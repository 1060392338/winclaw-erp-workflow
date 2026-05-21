#!/usr/bin/env python3.11
"""合规审查 → ERP认领 一体化脚本
用法:
  # 完整流程（认领到指定店铺）
  python3.11 run_compliance_claim.py --claim-to "順順の小屋童裝"

  # 只列出店铺不认领（Dry run，弹窗保持打开）
  python3.11 run_compliance_claim.py --list-stores

  # 继续认领（从上一次 --list-stores 的弹窗继续）
  python3.11 run_compliance_claim.py --claim-to "順順の小屋童裝"

流程: Playwright CDP → 货憨憨采集箱 → LLM图片+标题审查 → pass/reject → 认领到目标店铺
输出: ✅通过(N件) / ❌拒绝(N件) 详细理由

Agent 人设: 质检员 + 法条机 (OptimizerAgent)
  - 台湾合规5年经验，外号"照妖镜"
  - 思维流程: 看图片→看标题→下结论（不准跳步）
  - 淘汰原则: 宁漏3个能卖的，不放1个违规的
  - 复审确认: 翻盘违规判断需LLM复审
参见: agent_prompts.PROMPT_QUALITY_INSPECTOR, PROMPT_REGULATION_REF, PROMPT_QUALITY_REVIEW"""
import sys, json, time, random, os, argparse
from pathlib import Path
from dotenv import load_dotenv

PROJECT = Path(__file__).parent
sys.path.insert(0, str(PROJECT))
load_dotenv(PROJECT / ".env")

from models.schema import Product, ComplianceResult
from infrastructure.browser import BrowserManager
from infrastructure.erp_publisher import ERPPublisher
from infrastructure.compliance_checker import ComplianceChecker
from infrastructure.image_checker import ImageChecker
from infrastructure.taiwan_regulation import TaiwanRegulation
from infrastructure.title_optimizer import TitleOptimizer
from infrastructure.erp_publisher import ERPPublisher, delete_rejected_products, scan_unclaimed_products, _get_tab_count, _get_collect_box_pages

# 状态文件 — 保存合规结果供后续认领步骤读取
CLAIM_STATE_FILE = PROJECT / ".claim_state.json"
# 偏好店铺 — 用户上次选的店铺名，下次自动建议
PREFERRED_STORE_FILE = PROJECT / ".preferred_store"

def extract_unclaimed_products(page) -> list[dict]:
    """从ERP采集箱「未认领」tab提取所有商品数据（分页+窗口滚动全量扫描）

    使用 erp_publisher.scan_unclaimed_products() 三重策略扫描：
    ① tab 文本计数 — 权威数据源
    ② DOM 可见行快速提取
    ③ 窗口扩高+滚动渲染隐藏行（page-mode vue-recycle-scroller）

    支持跨页：翻页后每页都执行窗口滚动，确保不漏。去重合并后返回。
    """
    from infrastructure.config_loader import ConfigLoader
    _cc_cfg = ConfigLoader().load()
    # 三重保障导航：慢速+domcontentloaded+重试
    for _attempt in range(3):
        try:
            page.goto(f"{_cc_cfg.erp_url}/member/product/general/collect-box", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
            page.wait_for_load_state("networkidle", timeout=60000)
            break
        except Exception as _e:
            if _attempt < 2:
                print(f"  ⚠️ 导航采集箱被中断，第{_attempt+2}次重试...", flush=True)
                time.sleep(3)
            else:
                raise

    # 关闭弹窗
    try:
        page.evaluate("""() => {
            document.querySelectorAll('[class*="dialog"]').forEach(d => {
                const cb = d.querySelector('[class*="close"]');
                if (cb && typeof cb.click === 'function') cb.click();
            });
        }""")
    except Exception:
        pass
    time.sleep(2)

    # 切到「未认领」tab（用 JS 避免中文编码问题）
    page.evaluate("""() => {
        const tabs = document.querySelectorAll('[class*="t-tab"]');
        for (const t of tabs) {
            if (t.textContent.match(/未认领|鏈棰?/)) { t.click(); return; }
        }
    }""")
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(3)

    # 获取总页数 + tab 权威计数
    total_pages = _get_collect_box_pages(page)
    tab_count = _get_tab_count(page)
    print(f"  未认领: {tab_count} 件（页面计数）, 共 {total_pages} 页")

    all_products = []
    seen_ids = set()

    for pg in range(1, total_pages + 1):
        if pg > 1:
            # 切到下一页
            page.evaluate(f"""((n) => {{
                const pages = document.querySelectorAll('.t-pagination__number');
                for (const p of pages) {{
                    if (parseInt(p.textContent) === n) {{ p.click(); return; }}
                }}
            }})""", pg)
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(2000)

        # 使用 scan_unclaimed_products 做全量扫描（含窗口滚动）
        result = scan_unclaimed_products(page)
        page_products = result["products"]

        # 去重合并
        page_new = 0
        for p in page_products:
            pid = p.get("erp_id", "")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_products.append(p)
                page_new += 1
        print(f"    第{pg}页: 提取 {len(page_products)} 行, 新增 {page_new} 个商品")

    print(f"  共提取 {len(all_products)} 个商品")
    if len(all_products) < tab_count:
        print(f"  ⚠️ 虚拟滚动限制: 仅提取 {len(all_products)}/{tab_count} 件，差 {tab_count - len(all_products)} 件未渲染")
    return all_products


def run_compliance_and_claim(page, claim_store: str = "", dry_run: bool = False,
                              product_ids: set[str] | None = None,
                              resume_mode: bool = False,
                              claim_ids: list[str] | None = None) -> dict:
    """执行合规审查 + 认领（或仅 dry-run 列出店铺）

    Args:
        page: Playwright page
        claim_store: 目标店铺名。空则只列出店铺
        dry_run: 如果为True，只执行到弹出店铺列表，不确认认领
        product_ids: 指定货号过滤
        resume_mode: 从状态文件恢复（跳过提取+审查，直接用之前保存的pass_ids）

    Returns:
        dict 包含结果摘要
    """
    result = {
        "success": True,
        "summary": "",
        "products": [],
        "pass_count": 0,
        "reject_count": 0,
        "stores": [],
        "store_listed": False,
        "claimed": False,
    }
    reject_ids = []  # 质检员输出的不合规商品ID，供采集agent删除

    # ── 恢复模式在上面的提取步骤后处理，见第201行 ──
    
    # ── 正常模式：提取+审查 ──
    # 1. 提取未认领商品
    print("\n[1/5] 提取采集箱「未认领」商品...")
    raw = extract_unclaimed_products(page)
    print(f"  提取到 {len(raw)} 个商品")

    if not raw:
        result["summary"] = "⚠️ 无未认领商品"
        return result

    # 如果指定了商品ID，只保留匹配的商品
    if product_ids:
        raw = [r for r in raw if r.get("erp_id", "") in product_ids]
        if not raw:
            result["summary"] = f"⚠️ 未找到指定货号的未认领商品: {', '.join(product_ids)}"
            return result
        print(f"  → 过滤后: {len(raw)} 个商品匹配指定货号")

    for i, r in enumerate(raw):
        print(f"\n  商品 {i+1}:")
        print(f"    ERP ID: {r.get('erp_id', '?')}")
        print(f"    标题: {r.get('title', '?')[:60]}")
        print(f"    价格: CNY {r.get('price', 0)}")
        print(f"    状态: {r.get('status', '?')}")
        print(f"    图片: {r.get('img_url', '?')[:80]}")

    # 2. 如果恢复模式（从dry-run状态继续），跳过LLM合规审查，用保存的pass_ids
    pass_ids = None
    if resume_mode:
        if CLAIM_STATE_FILE.exists():
            state = json.loads(CLAIM_STATE_FILE.read_text(encoding="utf-8"))
            pass_ids = state.get("pass_ids", [])
        else:
            pass_ids = []
        if claim_ids:
            pass_ids = claim_ids
            print(f"  → 直接认领模式: {len(pass_ids)} 个商品", flush=True)
        check_count = len(pass_ids)
        print(f"  → 恢复模式: 使用dry-run保存的 {len(pass_ids)} 个通过商品ID，跳过二次LLM审查")
        print(f"  → 跳过合规审查（结果与dry-run一致）")
        # reject_ids 保持 []：恢复模式只做认领，删除操作在首次 run 时已由质检员输出
        # 用户需单独调 --delete-rejected 由搜货手执行删除，此处不重复处理
        # 步骤编号跳到勾选
        print(f"\n跳过 [2/5][3/5] → 直接进入 [4/5] 勾选+认领")
        print(f"\n[跳过] 合规审查结果:")
        print(f"  ✅ 使用dry-run通过的 {len(pass_ids)} 件商品")
        result["pass_count"] = len(pass_ids)
        result["summary"] = f"使用dry-run结果: 通过 {len(pass_ids)} 件"
    else:
        # 2. 构建 Product 对象 + 合规审查 (正常流程)
        print("\n[2/5] 合规审查...")
        print("  - 图片: OCR + qwen3-vl-plus 视觉")
        print("  - 标题: TaiwanRegulation")
        print("  - 优化: deepseek-v4-flash")

        products = []
        for r in raw:
            img_urls = [r.get("img_url", "")] if r.get("img_url") else []
            products.append(Product(
                id=r.get("erp_id", ""),
                title=r.get("title", f"商品{r.get('erp_id','')}"),
                price=r.get("price", 0),
                shop_name="拼多多",
                category="",
                image_urls=img_urls,
                erp_internal_id=r.get("erp_id", ""),
            ))

        image_checker = ImageChecker()
        regulation = TaiwanRegulation()
        title_optimizer = TitleOptimizer(regulation_checker=regulation)
        checker = ComplianceChecker(image_checker, regulation, title_optimizer)

        results = checker.review_batch(products)

        # 计算通过/拒绝商品列表
        pass_ids_list = checker.get_pass_ids(results)  # 先计算一次，后续复用
        all_ids = [r.get("erp_id", "") for r in raw]
        reject_ids = [rid for rid in all_ids if rid not in (pass_ids_list or [])]

    # 3. 输出审查结果
        print("\n[3/5] 合规审查结果:")
        print("-" * 60)
        for r in results:
            icon = {"pass": "✅", "title_optimized": "🔧", "reject": "❌"}.get(r.final_status, "❓")
            print(f"  {icon} [{r.final_status}] {r.product.title[:60]}")
            if r.title_issues:
                for issue in r.title_issues:
                    print(f"      ⚠️ {issue[:80]}")
            if r.optimized_title:
                print(f"      → 优化: {r.optimized_title[:60]}")
            if r.image_issues:
                for issue in r.image_issues:
                    print(f"      🖼️ {issue[:80]}")

        pass_ids = pass_ids_list  # 复用已计算的 pass_ids
        summary = checker.get_summary(results)
        print(f"\n  {summary}")

        result["pass_count"] = len(pass_ids)
        result["reject_count"] = len(results) - len(pass_ids)
        result["summary"] = summary
        result["pass_products"] = [{"id": r.product.id, "title": r.product.title, "category": r.product.category, "status": r.final_status} for r in results if r.final_status in ("pass", "title_optimized")]

        if not pass_ids:
            print("\n  ⚠️ 无合规商品可认领")
            return result

    # 4. 勾选商品 + 点击认领
    print(f"\n[4/5] 勾选 {len(pass_ids)} 个合规商品...")
    publisher = ERPPublisher(page=page)

    publisher.navigate_to_collection_box()
    time.sleep(2)

    # 关弹窗
    page.evaluate("""() => {
        document.querySelectorAll('[class*="dialog"]').forEach(d => {
            const cb = d.querySelector('[class*="close"]');
            if (cb && typeof cb.click === 'function') cb.click();
        });
    }""")
    time.sleep(1)

    # 切未认领tab（用 JS 避免中文编码问题）
    page.evaluate("""() => {
        const tabs = document.querySelectorAll('[class*="t-tab"]');
        for (const t of tabs) {
            if (t.textContent.match(/未认领|鏈棰?/)) { t.click(); return; }
        }
    }""")
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(2)

    # 用 JS 全量勾选 — 边滚动边勾选（解决 vue-recycle-scroller 回收 DOM 的问题）
    from infrastructure.erp_publisher import _get_collect_box_pages, _get_tab_count
    tab_count = _get_tab_count(page)
    pass_id_set = set(str(i) for i in pass_ids)
    
    # 扩高页面创造滚动空间
    page.evaluate("""() => {
        document.body.style.minHeight = "12000px";
        document.documentElement.style.minHeight = "12000px";
    }""")
    page.wait_for_timeout(500)
    
    # 边滚动边勾选：每次滚动后等 scroller 渲染完再扫描勾选
    check_count = 0
    prev_checked = 0
    stable_rounds = 0
    for i in range(150):
        page.evaluate("window.scrollTo(0, %d)" % (i * 80))
        page.wait_for_timeout(250)  # 给 scroller 足够时间渲染新行
        
        cnt = page.evaluate("""(ids) => {
            const idSet = new Set(ids.map(String));
            const rows = document.querySelectorAll('[class*="virtual-table-tr"]');
            let n = 0;
            rows.forEach(row => {
                const m = row.textContent.match(/货源ID[：:]\s*(\d+)/);
                if (m && idSet.has(m[1])) {
                    const cb = row.querySelector('input[type="checkbox"]');
                    if (cb && !cb.checked) {
                        cb.checked = true;
                        cb.dispatchEvent(new Event('change', { bubbles: true }));
                        n++;
                    }
                }
            });
            return n;
        }""", list(pass_id_set))
        
        check_count += cnt
        
        if cnt == 0:
            stable_rounds += 1
        else:
            stable_rounds = 0
        
        # 连续 30 轮无新增且已勾选数 >= tab_count 或 pass_ids 数 → 退出
        if stable_rounds >= 30 and check_count >= min(tab_count, len(pass_id_set)):
            break
        if stable_rounds >= 60:
            break
    
    # 恢复页面
    page.evaluate("""() => {
        window.scrollTo(0, 0);
        document.body.style.minHeight = "";
        document.documentElement.style.minHeight = "";
    }""")
    page.wait_for_timeout(300)
    
    print(f"  勾选 {check_count} 个商品")
    time.sleep(1)

    if check_count == 0:
        print("  ⚠️ 未勾选到商品")
        result["summary"] += " ⚠️ 未勾选到商品"
        return result

    # 点击认领
    print("  → 点击「认领」按钮...")
    publisher.click_claim()
    time.sleep(2)

    # 提取店铺列表
    stores = publisher.get_store_list_from_modal()
    result["stores"] = stores
    result["store_listed"] = True

    print(f"\n  可用店铺 ({len(stores)}):")
    for i, s in enumerate(stores):
        print(f"    {i+1}. {s['store_name']}")

    # 5. 保存状态文件（供后续 --claim-to 使用）
    state_data = {
        "pass_ids": pass_ids,
        "reject_ids": reject_ids,
        "check_count": check_count,
        "claim_store": "",
        "dry_run": dry_run,
    }
    CLAIM_STATE_FILE.write_text(json.dumps(state_data, ensure_ascii=False, indent=2))

    if dry_run:
        # Dry-run 模式：列出店铺后退出，不确认
        store_names = [s["store_name"] for s in stores]
        preferred = PREFERRED_STORE_FILE.read_text(encoding="utf-8").strip() if PREFERRED_STORE_FILE.exists() else ""

        if preferred:
            result["summary"] = f"合规通过 {len(pass_ids)} 件。上次认领到「{preferred}」，可以继续或用 {{换一个新店}}"
            result["preferred_store"] = preferred
        else:
            result["summary"] = f"合规通过 {len(pass_ids)} 件。可用店铺: {', '.join(store_names)}"
        # 🔴 自动删除不合规商品：reject_ids 直接从采集箱删除
        if reject_ids:
            print(f"\n  🗑️  自动删除 {len(reject_ids)} 个不合规商品: {', '.join(reject_ids)}")
            try:
                delete_rejected_products(page, set(reject_ids))
                # 删除成功后清掉状态文件中的 reject_ids
                state_data["reject_ids"] = []
                CLAIM_STATE_FILE.write_text(json.dumps(state_data, ensure_ascii=False, indent=2))
                print(f"  ✅ 已从采集箱删除 {len(reject_ids)} 个不合规商品")
            except Exception as e:
                print(f"  ⚠️ 删除异常: {e}")
        else:
            print(f"  ℹ️  无不合规商品需删除")
        
        print(f"\n  ℹ️  Dry-run 模式，未确认认领")
        print(f"  可用店铺：{', '.join(store_names)}")
        return result

    # 5. 选择店铺 + 确认认领
    print(f"\n[5/5] 认领到店铺: {claim_store}")
    if not claim_store:
        print("  ⚠️ 未指定目标店铺，跳过认领")
        result["summary"] += " ⚠️ 未指定店铺"
        return result

    chosen = None
    for s in stores:
        if claim_store.strip() in s["store_name"]:
            chosen = s
            break
    if not chosen:
        print(f"  ❌ 未找到目标店铺 '{claim_store}'")
        print(f"  可用店铺: {[s['store_name'] for s in stores]}")
        result["summary"] += f" ❌ 未找到店铺 '{claim_store}'"
        result["success"] = False
        return result

    print(f"  → 选择: {chosen['store_name']}")
    publisher.select_store(chosen["store_name"])
    time.sleep(0.5)
    publisher.confirm_claim()

    # 获取本次认领商品的主货号 — 从已勾选的 checkbox 中提取，不是全量读草稿箱
    claimed_ids = []
    try:
        # 认领完成后弹窗关闭，在采集箱页面直接读 checkbox 已选行的主货号
        time.sleep(2)
        claimed_ids = page.evaluate("""() => {
            var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
            var ids = [];
            for (var i = 0; i < rows.length; i++) {
                var cb = rows[i].querySelector('input[type="checkbox"]');
                if (cb && (cb.checked || cb.getAttribute('checked') !== null)) {
                    var text = rows[i].textContent;
                    var m = text.match(/主货号[：:]\s*(\d+)/);
                    if (m) ids.push(m[1]);
                }
            }
            return ids;
        }""")
        if claimed_ids:
            print(f"  ??? 获取认领主货号: {len(claimed_ids)} 件")
        else:
            # 兜底：从 pass_ids 构造主货号
            claimed_ids = [str(pid) for pid in (pass_ids or [])]
            print(f"  ??? 从pass_ids获取主货号: {len(claimed_ids)} 件")
    except Exception as e:
        print(f"  ?? 获取主货号失败: {e}")
        claimed_ids = [str(pid) for pid in (pass_ids or [])]

    result["claimed"] = True
    result["claimed_product_ids"] = claimed_ids
    result["claimed_product_ids"] = claimed_ids
    result["summary"] = f"✅ 认领完成! 店铺: {chosen['store_name']}, 商品数: {len(pass_ids)}, 主货号: {len(claimed_ids)}件"
    result["preferred_store"] = chosen["store_name"]

    # 保存偏好店铺
    PREFERRED_STORE_FILE.write_text(chosen["store_name"], encoding="utf-8")

    # 清理状态文件 — 只清 pass_ids，保留 reject_ids 供 --delete-rejected 用
    if CLAIM_STATE_FILE.exists():
        try:
            state = json.loads(CLAIM_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            state = {"pass_ids": [], "reject_ids": [], "check_count": 0, "claimed": True}
        state["pass_ids"] = []
        state["claimed"] = True
        state["check_count"] = 0
        CLAIM_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    return result


def main():
    parser = argparse.ArgumentParser(description="ERP合规审查+认领")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list-stores", action="store_true",
                       help="Dry-run: 执行合规审查→勾选→点击认领→列出店铺，不确认")
    group.add_argument("--claim-to", type=str, default="",
                       help="认领到指定店铺（如「順順の小屋童裝」）")
    parser.add_argument("--resume", action="store_true",
                       help="从状态文件恢复（弹窗应保持打开）")
    parser.add_argument("--products", type=str, default="",
                       help="指定货号(逗号分隔)，只处理这些商品（如 742642150541,825171316474）")
    parser.add_argument("--claim-ids", type=str, default="",
                       help="认领时只认领指定ID列表（逗号分隔），覆盖状态文件中的pass_ids")
    parser.add_argument("--direct-claim", type=str, default="",
                       help="直接认领模式：传入主货号列表（逗号分隔），不依赖状态文件")
    parser.add_argument("--delete-rejected", action="store_true",
                       help="删除不合规商品（从.claim_state.json读取reject_ids，供采集agent调用）")
    parser.add_argument("--cdp-port", type=int, default=None,
                       help="Chrome CDP 端口（默认自动扫描 9222-9229）")
    args = parser.parse_args()

    # --direct-claim 直接认领模式（不依赖状态文件）
    if args.direct_claim:
        if not args.claim_to:
            print("❌ 直接认领模式需要 --claim-to 指定店铺")
            return 1
        direct_ids = [i.strip() for i in args.direct_claim.split(",") if i.strip()]
        if not direct_ids:
            print("❌ 请传入要认领的主货号")
            return 1
        print(f"  -> direct claim: {len(direct_ids)} items to {args.claim_to}", flush=True)
        bm = BrowserManager(cdp_ports=[args.cdp_port] if args.cdp_port else None)
        bm.connect()
        print("  ✅ 已连接 Chrome")
        result = run_compliance_and_claim(
            page=bm.page, claim_store=args.claim_to, dry_run=False,
            resume_mode=True, claim_ids=direct_ids,
        )
        result["pass_count"] = len(direct_ids)
        print(f"\n{'=' * 60}")
        print(f"📋 结果: {result['summary']}")
        print(f"{'=' * 60}")
        pass_products = result.get("pass_products", [])
        json_out = {"success": result["success"], "summary": result["summary"],
            "pass_count": result["pass_count"], "claimed_product_ids": result.get("claimed_product_ids", []),
            "pass_products": pass_products}
        print(f"\n--JSON--\n{json.dumps(json_out, ensure_ascii=False)}")
        return 0 if result["success"] else 1

    # --delete-rejected 独立处理    if args.delete_rejected:
        if not CLAIM_STATE_FILE.exists():
            print("❌ 无状态文件，请先运行 --list-stores 或 --claim-to")
            return 1
        state = json.loads(CLAIM_STATE_FILE.read_text(encoding="utf-8"))
        rids = state.get("reject_ids", [])
        if not rids:
            print("ℹ️  无不合规商品需删除")
            return 0
        print(f"🗑️  删除 {len(rids)} 个不合规商品: {', '.join(rids)}")
        bm = BrowserManager(cdp_ports=[args.cdp_port] if args.cdp_port else None)
        bm.connect()
        print("  ✅ 已连接 Chrome")
        delete_rejected_products(bm.page, rids)
        # 删除成功 → 清掉 state 中的 reject_ids（如果 pass_ids 也为空则全删）
        state["reject_ids"] = []
        if not state.get("pass_ids"):
            CLAIM_STATE_FILE.unlink(missing_ok=True)
        else:
            CLAIM_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    # 检测是从 --list-stores 恢复（弹窗已打开），排除已认领的旧状态
    resume_mode = False
    if args.resume:
        resume_mode = True
    elif CLAIM_STATE_FILE.exists():
        try:
            st = json.loads(CLAIM_STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            st = {}
        resume_mode = not st.get("claimed", False)

    print("=" * 60)
    mode = "Dry-run 列出店铺" if args.list_stores else f"认领到: {args.claim_to or '(等待指定)'}"
    if resume_mode and not args.list_stores:
        mode = f"恢复认领 → {args.claim_to or '(使用状态文件)'}"
    print(f"🔍 ERP 合规审查 → 认领 [{mode}]")
    print("=" * 60)

    bm = BrowserManager(cdp_ports=[args.cdp_port] if args.cdp_port else None)
    try:
        bm.connect()
        print("  ✅ 已连接 Chrome")
    except Exception as e:
        print(f"  ❌ 连接失败: {e}")
        return 1

    try:
        # 解析指定商品ID
        product_ids = set(args.products.split(",")) if args.products else None

        result = run_compliance_and_claim(
            page=bm.page,
            claim_store=args.claim_to,
            dry_run=args.list_stores,
            product_ids=product_ids,
            resume_mode=resume_mode,
        )

        print(f"\n{'=' * 60}")
        print(f"📋 结果: {result['summary']}")
        print(f"{'=' * 60}")

        if result["stores"]:
            print(f"\n可用店铺列表:")
            for i, s in enumerate(result["stores"]):
                print(f"  {i+1}. {s['store_name']}")

        # JSON 输出供编排器解析
        pass_products = result.get("pass_products", [])
        json_out = {
            "success": result["success"],
            "summary": result["summary"],
            "pass_count": result["pass_count"],
            "reject_count": result["reject_count"],
            "pass_products": pass_products,
            "stores": [s["store_name"] for s in result["stores"]],
            "store_listed": result["store_listed"],
            "claimed": result["claimed"],
            "preferred_store": result.get("preferred_store", ""),
            "claimed_product_ids": result.get("claimed_product_ids", []),
        }
        print(f"\n--JSON--\n{json.dumps(json_out, ensure_ascii=False)}")

        return 0 if result["success"] else 1

    except Exception as e:
        print(f"\n  ❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
