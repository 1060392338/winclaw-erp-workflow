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
from config.selectors import SEL, TXT, T, C, close_dialogs, switch_tab, expand_and_scroll, recover_page, wait_visible, wait_dialog, sleep

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
            page.goto(f"{_cc_cfg.erp_url}/member/product/general/collect-box", wait_until="domcontentloaded", timeout=T.NAVIGATION)
            sleep(T.THREE_SECONDS)
            page.wait_for_load_state("networkidle", timeout=T.NAVIGATION)
            break
        except Exception as _e:
            if _attempt < 2:
                print(f"  ⚠️ 导航采集箱被中断，第{_attempt+2}次重试...", flush=True)
                sleep(T.THREE_SECONDS)
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
    sleep(T.TWO_SECONDS)

    # 切到「未认领」tab（用 JS 避免中文编码问题）
    page.evaluate("""(sel) => {
        const tabs = document.querySelectorAll(sel);
        for (const t of tabs) {
            if (t.textContent.match(/未认领|鏈棰?/)) { t.click(); return; }
        }
    }""", SEL.TAB)
    page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)
    sleep(T.THREE_SECONDS)

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
                              skip_image: bool = False,
                              claim_ids: list[str] | None = None,
                              review_only: bool = False) -> dict:
    """执行合规审查 + 认领（或仅审查）

    Args:
        page: Playwright page
        claim_store: 目标店铺名。空则只列出店铺
        dry_run: 如果为True，只执行到弹出店铺列表，不确认认领
        product_ids: 指定货号过滤
        resume_mode: 从状态文件恢复（跳过提取+审查，直接用之前保存的pass_ids）
        skip_image: 跳过图片审查
        claim_ids: 认领时只认领指定ID列表（覆盖状态文件中的pass_ids）
        review_only: 只做审查+删除不合规，不认领。过审但未分配类目的商品留在采集箱

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
        reject_ids = []  # 恢复模式：reject已在首次运行时存入状态文件，不重复计算
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

        # 使用并发审查（5线程），大幅提速；skip_image 传入控制图片审查
        def _progress_cb(done, total, title):
            print(f"  📊 审查进度: {done}/{total} ({title}...)", flush=True)

        results = checker.review_batch_concurrent(
            products, max_workers=5, timeout=60,
            on_progress=_progress_cb, skip_image=skip_image,
        )

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
        result["reject_products"] = [{"id": r.product.id, "title": r.product.title, "category": r.product.category, "status": r.final_status, "issues": (r.title_issues or []) + (r.image_issues or [])} for r in results if r.final_status == "reject"]

        if not pass_ids:
            print("\n  ⚠️ 无合规商品可认领")
            return result

    # ── review_only 模式：审查完毕，只删除不合规，不认领 ──
    if review_only:
        print(f"\n  📋 审查完毕（review-only 模式，不认领）")
        print(f"  ✅ 过审 {len(pass_ids)} 件 | ❌ 不合规 {len(reject_ids)} 件")
        print(f"  ℹ️  过审商品留在采集箱，等待分配类目后用 --direct-claim 认领")

        # 保存状态文件（含 pass_ids 和 reject_ids）
        state_data = {
            "pass_ids": list(set(str(i) for i in pass_ids)),
            "reject_ids": reject_ids,
            "check_count": 0,
            "claim_store": "",
            "review_only": True,
        }
        CLAIM_STATE_FILE.write_text(json.dumps(state_data, ensure_ascii=False, indent=2))

        # 删除不合规商品
        if reject_ids:
            print(f"\n  🗑️  删除 {len(reject_ids)} 个不合规商品: {', '.join(reject_ids)}")
            # 需要先勾选不合规商品才能删除
            publisher = ERPPublisher(page=page)
            publisher.navigate_to_collection_box()
            sleep(T.TWO_SECONDS)
            # 关弹窗
            page.evaluate("""() => {
                document.querySelectorAll('[class*="dialog"]').forEach(d => {
                    const cb = d.querySelector('[class*="close"]');
                    if (cb && typeof cb.click === 'function') cb.click();
                });
            }""")
            sleep(T.ONE_SECOND)
            # 切未认领tab
            from config.selectors import switch_tab
            switch_tab(page, TXT.TAB_UNCLAIMED)
            page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)
            sleep(T.TWO_SECONDS)
            try:
                delete_rejected_products(page, set(reject_ids))
                state_data["reject_ids"] = []
                CLAIM_STATE_FILE.write_text(json.dumps(state_data, ensure_ascii=False, indent=2))
                print(f"  ✅ 已从采集箱删除不合规商品")
            except Exception as e:
                print(f"  ⚠️ 删除异常: {e}")

        result["summary"] = f"审查完毕: 过审 {len(pass_ids)} 件, 不合规 {len(reject_ids)} 件（已删除）, 过审商品留在采集箱"
        result["review_only"] = True

        # JSON 输出供编排器解析
        pass_products_out = result.get("pass_products", [])
        reject_products_out = result.get("reject_products", [])
        json_out = {
            "success": result["success"],
            "summary": result["summary"],
            "pass_count": result["pass_count"],
            "reject_count": result["reject_count"],
            "pass_products": pass_products_out,
            "reject_products": reject_products_out,
            "stores": [],
            "store_listed": False,
            "claimed": False,
            "preferred_store": "",
            "claimed_product_ids": [],
            "review_only": True,
        }
        print(f"\n--JSON--\n{json.dumps(json_out, ensure_ascii=False)}")

        return result
    print(f"\n[4/5] 勾选 {len(pass_ids)} 个合规商品...")
    publisher = ERPPublisher(page=page)

    publisher.navigate_to_collection_box()
    sleep(T.TWO_SECONDS)

    # 关弹窗
    page.evaluate("""() => {
        document.querySelectorAll('[class*="dialog"]').forEach(d => {
            const cb = d.querySelector('[class*="close"]');
            if (cb && typeof cb.click === 'function') cb.click();
        });
    }""")
    sleep(T.ONE_SECOND)

    # 切未认领tab（用 JS 避免中文编码问题）
    page.evaluate("""(sel) => {
        const tabs = document.querySelectorAll(sel);
        for (const t of tabs) {
            if (t.textContent.match(/未认领|鏈棰?/)) { t.click(); return; }
        }
    }""", SEL.TAB)
    page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)
    sleep(T.TWO_SECONDS)

    # ── Claim-and-Replace 循环策略 ──
    # 用户方案：先扫第1页可视行做ID匹配→勾选→认领→认领后已认领商品从「未认领」tab消失
    # 后续页内容自动填充到第1页→继续扫第1页→循环直到全部ID被认领或无匹配
    # 页面模式(page-mode) → window.scrollTo 或 scroller.scrollTop
    # 内部滚动模式 → scroller.scrollTop
    from infrastructure.erp_publisher import _get_tab_count
    pass_id_set = set(str(i) for i in pass_ids)
    claimed_set = set()
    stores = []

    # ── 单页快速检测 ──
    # ERP 每页固定 20 条，tab 计数 ≤ 20 就是单页
    tab_count = _get_tab_count(page)
    is_single_page = tab_count <= C.PAGE_SIZE
    if is_single_page:
        print(f"  ⚡ 单页快速通道: tab计数 {tab_count} ≤ 20，所有商品一次勾选")
    else:
        print(f"  🔄 多页模式: tab计数 {tab_count} > 20，逐页触发+第1页勾选认领")
        print(f"     策略: 第1页可见行匹配→勾选→认领→翻到第2页再翻回→第2页内容填充到第1页→继续")

    # ── 认领循环：逐页扫描，动态调整页数，翻页重试保留勾选ID ──
    scan_page = 1

    while len(claimed_set) < len(pass_id_set) and scan_page <= 99:
        total_pages = _get_collect_box_pages(page)

        if scan_page > total_pages:
            print(f"  ℹ️ 已扫描至第{total_pages}页（共{total_pages}页），结束")
            break

        if scan_page > 1:
            print(f"  📄 翻到第{scan_page}页...")
            page.evaluate("""(n) => {
                const pages = document.querySelectorAll('.t-pagination__number');
                for (const p of pages) {
                    if (parseInt(p.textContent) === n) { p.click(); return; }
                }
            }""", scan_page)
            page.wait_for_load_state("networkidle", timeout=15000)
            sleep(T.TWO_SECONDS)

        # 扩高+全量滚动，触虚拟滚动渲染当前页所有行（解决提取不全）
        expand_and_scroll(page, height=C.EXPANDED_HEIGHT_PER_PAGE * 2)
        page.evaluate("window.scrollTo(0, 0)")
        sleep(T.SCROLL_RECOVER)

        # 在当前页找待认领ID
        visible_targets = page.evaluate("""({targets, claimed}) => {
            const targetSet = new Set(targets);
            const claimedSet = new Set(claimed);
            const match = [];
            document.querySelectorAll('[class*="virtual-table-tr"]').forEach(row => {
                const m = row.textContent.match(/货源ID[：:]\s*(\d+)/);
                if (m && targetSet.has(m[1]) && !claimedSet.has(m[1])) {
                    match.push(m[1]);
                }
            });
            return match;
        }""", {"targets": list(pass_id_set), "claimed": list(claimed_set)})

        if not visible_targets:
            scan_page += 1
            continue

        # 勾选 → 认领
        checked = page.evaluate("""(ids) => {
            const idSet = new Set(ids);
            let n = 0;
            document.querySelectorAll('[class*="virtual-table-tr"]').forEach(row => {
                const m = row.textContent.match(/货源ID[：:]\s*(\d+)/);
                if (m && idSet.has(m[1])) {
                    const cb = row.querySelector('input[type="checkbox"]');
                    if (cb && !cb.checked) {
                        cb.click();
                        n++;
                    }
                }
            });
            return n;
        }""", visible_targets)

        print(f"  第{scan_page}页: 勾选 {checked} 个 → 认领...")

        # 点击认领（如果按钮不可用，记住ID翻回第1页重试）
        claimed_this_round = list(visible_targets)
        publisher.click_claim()
        try:
            page.wait_for_selector(SEL.DIALOG_VISIBLE_ALL, timeout=T.DIALOG_APPEAR)
            sleep(T.ONE_SECOND)
        except Exception:
            print(f"  ⚠️ 第{scan_page}页认领按钮不可用，记住ID翻回第1页重试")
            page.evaluate("""() => {
                const pages = document.querySelectorAll('.t-pagination__number');
                for (const p of pages) { if (parseInt(p.textContent) === 1) { p.click(); return; } }
            }""")
            page.wait_for_load_state("networkidle", timeout=15000)
            sleep(T.TWO_SECONDS)
            # 翻回第1页后重新勾选这批ID
            rechecked = page.evaluate("""(ids) => {
                const idSet = new Set(ids);
                let n = 0;
                document.querySelectorAll('[class*="virtual-table-tr"]').forEach(row => {
                    const m = row.textContent.match(/货源ID[：:]\s*(\d+)/);
                    if (m && idSet.has(m[1])) {
                        const cb = row.querySelector('input[type="checkbox"]');
                        if (cb && !cb.checked) { cb.click(); n++; }
                    }
                });
                return n;
            }""", claimed_this_round)
            print(f"  ↪ 翻回第1页重新勾选 {rechecked}/{len(claimed_this_round)} 个")
            publisher.click_claim()
            try:
                page.wait_for_selector(SEL.DIALOG_VISIBLE_ALL, timeout=T.DIALOG_APPEAR)
                sleep(T.ONE_SECOND)
            except Exception:
                print("  ⚠️ 翻回第1页后认领仍异常，跳过这批")
                page.evaluate("""() => {
                    document.querySelectorAll('[class*="dialog"] [class*="close"]').forEach(c => c.click());
                }""")
                sleep(T.ONE_SECOND)
                continue

        # 获取店铺列表（只第一轮取一次）
        if scan_page == 1 and not stores:
            stores = publisher.get_store_list_from_modal(max_retries=3)
            result["stores"] = stores
            result["store_listed"] = True
            if not dry_run and stores:
                print(f"\n  可用店铺 ({len(stores)}):")
                for i, s in enumerate(stores):
                    print(f"    {i+1}. {s['store_name']}")

        if dry_run:
            store_names = [s["store_name"] for s in (stores or [])]
            preferred = PREFERRED_STORE_FILE.read_text(encoding="utf-8").strip() if PREFERRED_STORE_FILE.exists() else ""
            if preferred:
                result["summary"] = f"合规通过 {len(pass_ids)} 件。上次认领到「{preferred}」，可以继续或用{{换一个新店}}"
                result["preferred_store"] = preferred
            else:
                result["summary"] = f"合规通过 {len(pass_ids)} 件。可用店铺: {', '.join(store_names)}"
            page.evaluate("""(closeSel) => {
                const closes = document.querySelectorAll(closeSel);
                for (const c of closes) { if(c.offsetParent !== null) c.click(); }
            }""", SEL.DIALOG_CLOSE + ', [class*="dialog"] [class*="close"]')
            print(f"  可用店铺：{', '.join(store_names)}")
            return result

        if claim_store:
            chosen = None
            for s in (stores or []):
                if claim_store.strip() in s["store_name"]:
                    chosen = s
                    break
            if not chosen:
                print(f"  ❌ 未找到目标店铺 '{claim_store}'")
                print(f"  可用店铺: {[s['store_name'] for s in (stores or [])]}")
                result["summary"] += f" ❌ 未找到店铺 '{claim_store}'"
                result["success"] = False
                return result
            print(f"  → 选择: {chosen['store_name']}")
            publisher.select_store(chosen["store_name"])
            sleep(T.HALF_SECOND)
            publisher.confirm_claim()
            sleep(T.TWO_SECONDS)

        # 关弹窗
        try:
            page.evaluate("""(closeSel) => {
                const closes = document.querySelectorAll(closeSel);
                for (const c of closes) { if(c.offsetParent !== null) c.click(); }
            }""", SEL.DIALOG_CLOSE + ', [class*="dialog"] [class*="close"]')
            sleep(T.HALF_SECOND)
        except Exception:
            pass

        claimed_set.update(claimed_this_round)
        print(f"  ✅ 第{scan_page}页完成，累计认领: {len(claimed_set)}/{len(pass_id_set)}")

        # 认领后不跳页，让循环重新扫当前页（已认领消失后后续页自动填充）
        # 但如果当前页已无目标，scan_page保持当前值，下次循环会扫同一页

    # 认领循环结束，汇总结果
    check_count = len(claimed_set)
    pass_ids_actual = list(claimed_set)
    print(f"\n  最终认领 {check_count}/{len(pass_id_set)} 个商品")

    if check_count == 0:
        print("  ⚠️ 未认领到任何商品")
        result["summary"] += " ⚠️ 未认领到商品"
        return result

    if check_count < len(pass_id_set):
        print(f"  ⚠️ 部分商品未认领 {check_count}/{len(pass_id_set)}")

    claimed_ids = list(claimed_set) if claimed_set else pass_ids_actual
    result["claimed"] = True
    result["claimed_product_ids"] = claimed_ids
    result["pass_count"] = len(claimed_ids)

    if claim_store:
        PREFERRED_STORE_FILE.write_text(claim_store, encoding="utf-8")
        result["summary"] = f"✅ 认领完成! 店铺: {claim_store}, 商品数: {len(claimed_ids)}件"
        result["preferred_store"] = claim_store
    else:
        result["summary"] = f"✅ 认领完成! 商品数: {len(claimed_ids)}件"

    # 清理状态文件
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
    parser.add_argument("--skip-image", action="store_true",
                       help="跳过图片审查，只做标题审查")
    parser.add_argument("--review-only", action="store_true",
                       help="只做审查+删除不合规，不认领。过审商品留在采集箱，等待分配类目后用 --direct-claim 认领")
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
            skip_image=args.skip_image,
        )
        result["pass_count"] = len(direct_ids)
        print(f"\n{'=' * 60}")
        print(f"📋 结果: {result['summary']}")
        print(f"{'=' * 60}")
        pass_products = result.get("pass_products", [])
        json_out = {"success": result["success"], "summary": result["summary"],
            "pass_count": result["pass_count"], "claimed_product_ids": result.get("claimed_product_ids", []),
            "pass_products": pass_products, "reject_products": result.get("reject_products", [])}
        print(f"\n--JSON--\n{json.dumps(json_out, ensure_ascii=False)}")
        return 0 if result["success"] else 1

    # --delete-rejected 独立处理
    if args.delete_rejected:
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
    if args.review_only:
        mode = "仅审查（不认领，过审商品留在采集箱）"
    elif args.list_stores:
        mode = "Dry-run 列出店铺"
    else:
        mode = f"认领到: {args.claim_to or '(等待指定)'}"
    if resume_mode and not args.list_stores and not args.review_only:
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
            skip_image=args.skip_image,
            review_only=args.review_only,
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
        reject_products = result.get("reject_products", [])
        json_out = {
            "success": result["success"],
            "summary": result["summary"],
            "pass_count": result["pass_count"],
            "reject_count": result["reject_count"],
            "pass_products": pass_products,
            "reject_products": reject_products,
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
