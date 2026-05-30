#!/usr/bin/env python3
"""
直接发布 — 基于 publish_final.py 成功经验
用 locator API 检测弹窗保存按钮，不依赖 JS evaluate。

用法:
    python publish_direct.py "順順の小屋童裝（本土）" --products id1,id2
    python publish_direct.py "順順の小屋童裝（本土）" --all
"""
import sys, time, re, argparse
from config.selectors import SEL, TXT, T, C, close_dialogs, switch_tab, expand_and_scroll, recover_page, wait_visible, wait_dialog, sleep
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from infrastructure.config_loader import ConfigLoader

def main():
    parser = argparse.ArgumentParser(description="直接发布（locator弹窗版）")
    parser.add_argument("store", help="目标店铺")
    parser.add_argument("--check-product", help="只校验指定主货号是否在发布页，不发布")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--products", help="主货号，逗号分隔")
    group.add_argument("--all", action="store_true", help="发布全部草稿")
    args = parser.parse_args()

    store = args.store
    target_ids = set(args.products.split(",")) if args.products else None

    # 场景: 只校验不发布（供 run_workflow.py 轮询调用）
    # 选店铺 → 逐tab（发布中/发布成功/发布失败）读取页面文本，找主货号
    if args.check_product:
        check_pid = args.check_product
        _cfg2 = ConfigLoader().load()
        port2 = _cfg2.erp_cdp_ports[0]
        p2 = sync_playwright().start()
        b2 = p2.chromium.connect_over_cdp(f"http://127.0.0.1:{port2}")
        page2 = b2.contexts[0].pages[0]
        page2.goto(f"{_cfg2.erp_url}/member/product/shopee/publish", wait_until="networkidle", timeout=T.NETWORK_IDLE)
        sleep(T.PUBLISH_INITIAL)

        # 选店铺
        if store:
            tags2 = page2.locator('.t-tag--check')
            for i in range(tags2.count()):
                txt = tags2.nth(i).text_content()
                if txt == store:
                    tags2.nth(i).click()
                    break
            sleep(200)
            page2.locator('button:has-text("查询")').first.click()
            sleep(1000)

        # 逐tab查找：只看发布中/发布成功/发布失败（不看草稿箱）
        found = False
        for tab_text in [TXT.TAB_PUBLISHING, TXT.TAB_PUBLISH_SUCCESS, TXT.TAB_PUBLISH_FAIL]:
            tab = page2.locator(f'text={tab_text}').first
            if tab.count() > 0:
                tab.click()
                sleep(800)
                body2 = page2.evaluate('document.body.innerText')
                if check_pid in body2:
                    found = True
                    break

        print(f"CHECK_PRODUCT:{check_pid}:{'FOUND' if found else 'NOT_FOUND'}", flush=True)
        p2.stop()
        return 0 if found else 1

    print("=" * 60)
    print("📦 Shopee 批量发布 (直接版)")
    print(f"   店铺: {store}")
    if target_ids:
        print(f"   货号: {len(target_ids)} 个")
    elif args.all:
        print(f"   范围: 全部草稿")
    print("=" * 60)

    _cfg = ConfigLoader().load()
    port = _cfg.erp_cdp_ports[0]

    p = sync_playwright().start()
    b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    page = b.contexts[0].pages[0]

    # 导航到发布页
    page.goto(f"{_cfg.erp_url}/member/product/shopee/publish", wait_until="networkidle", timeout=T.NETWORK_IDLE)
    sleep(2000)  # 等弹窗组件就绪
    print("[1/4] 导航完成", flush=True)

    # 切草稿箱
    page.locator('text=草稿箱').first.click()
    sleep(800)
    print("[2/4] 草稿箱", flush=True)

    # 选店铺 — 统一用模糊匹配（精确匹配已废弃：tag-group分组定位不可靠）
    # 跨所有标签组遍历 .t-tag--check，先尝试精确匹配，再试模糊匹配
    target_clicked = False
    tags = page.locator('.t-tag--check')
    
    # 1) 先做精确匹配
    for i in range(tags.count()):
        txt = tags.nth(i).text_content()
        if txt == store:
            cls = tags.nth(i).get_attribute('class') or ''
            if 't-tag--checked' not in cls:
                tags.nth(i).click()
                print(f"  选中店铺: {txt}", flush=True)
            else:
                print(f"  店铺已选中: {txt}", flush=True)
            target_clicked = True
            break
    
    # 2) 精确匹配失败 → 模糊匹配（稳定路径）
    if not target_clicked:
        print(f"  精确匹配未命中 [{store}]，走模糊匹配", flush=True)
        for i in range(tags.count()):
            txt = tags.nth(i).text_content()
            # 去括号模糊匹配
            bare_store = store.replace('（本土）','').replace('(本土)','').replace('（本土','').replace('(本土','')
            bare_txt = txt.replace('（本土）','').replace('(本土)','').replace('（本土','').replace('(本土','')
            if bare_store in bare_txt or bare_txt in bare_store:
                tags.nth(i).click()
                print(f"  模糊匹配选中: {txt}", flush=True)
                target_clicked = True
                break
    
    if not target_clicked:
        print(f"  ⚠️ 未找到店铺 [{store}]（精确+模糊均未命中）", flush=True)
    sleep(200)
    page.locator('button:has-text("查询")').first.click()
    sleep(1500)

    if target_ids:
        # 按ID匹配勾选 — 用 claim-and-replace 循环策略（支持跨页）
        # 原理：发布后已发布商品从草稿箱消失，后续页自动填充到第1页
        remaining = set(target_ids)
        target_strs = set(str(i) for i in target_ids)
        total_checked = 0
        max_rounds = len(target_ids) + C.PUBLISH_REPLACE_OFFSET
        saved_publish = False
        draft_count = page.evaluate("""(sel) => {
            const tabs = document.querySelectorAll(sel);
            for (const t of tabs) {
                const m = t.textContent.match(/\\u8349\\u7a3f\\u7bb1[\\uff08(](\\d+)[\\uff09)]/);
                if (m) return parseInt(m[1]);
            }
            return 0;
        }""", SEL.TAB)
        is_single_page = draft_count <= C.PAGE_SIZE
        if is_single_page:
            print(f"  ⚡ 单页快速通道: 草稿箱{draft_count}件 ≤ 20")
        else:
            print(f"  🔄 多页模式: 草稿箱{draft_count}件 > 20，进入循环")

        for rnd in range(1, max_rounds + 1):
            if not remaining:
                break

            # 取消所有勾选
            page.evaluate(f"() => {{ document.querySelectorAll('{SEL.CHECKBOX}').forEach(cb => {{if(cb.checked) cb.click();}}); }}")
            sleep(T.SCROLL_RECOVER)

            # 扫第1页可视行，匹配剩余ID
            visible_ids = page.evaluate("""({ids, tablerow}) => {
                const targetSet = new Set(ids);
                const found = [];
                document.querySelectorAll(tablerow).forEach(row => {
                    const text = row.textContent;
                    if (text.length < 30) return;
                    for (const id of targetSet) {
                        if (text.includes(id)) {
                            found.push(id);
                            break;
                        }
                    }
                });
                return found;
            }""", {"ids": list(remaining), "tablerow": SEL.TABLE_ROW})

            if not visible_ids:
                break

            # 勾选匹配的行
            checked = page.evaluate("""({ids, tablerow}) => {
                const idSet = new Set(ids);
                let n = 0;
                document.querySelectorAll(tablerow).forEach(row => {
                    const text = row.textContent;
                    if (text.length < 30) return;
                    for (const id of idSet) {
                        if (text.includes(id)) {
                            const cb = row.querySelector('input[type="checkbox"]');
                            if (cb && !cb.checked) {
                                cb.checked = true;
                                cb.dispatchEvent(new Event('change', {bubbles: true}));
                                n++;
                            }
                            break;
                        }
                    }
                });
                return n;
            }""", {"ids": visible_ids, "tablerow": SEL.TABLE_ROW})

            if checked == 0:
                break

            total_checked += checked
            print(f"  第{rnd}轮: 勾选 {checked} 个 (累计 {total_checked}/{len(target_ids)})", flush=True)

            # 产品发布 hover+click
            page.locator(f'button:has-text("{TXT.BTN_PUBLISH}")').first.hover()
            sleep(100)
            page.locator(f'button:has-text("{TXT.BTN_PUBLISH}")').first.click()
            sleep(600)

            # 立即发布
            page.locator('.t-dropdown__item-text').filter(has_text="立即发布").first.click()
            sleep(400)

            # 处理弹窗
            saved_publish = False
            for _ in range(20):
                body = page.evaluate('document.body.innerText')

                # 路径A: 未设置类目弹窗 → 跳过
                if ('跳过未设置类目产品并继续发布' in body or '璺宠繃鏈缃被鐩骇' in body):
                    try:
                        page.locator('text=跳过未设置类目产品并继续发布').first.click(timeout=T.ELEMENT_VISIBLE)
                    except:
                        page.evaluate("""() => {
                            const btns = document.querySelectorAll('[class*="dialog"] button, [class*="dialog"] span');
                            for (const btn of btns) {
                                if (btn.textContent.includes('跳过') || btn.textContent.includes('璺宠繃')) {
                                    btn.click(); return;
                                }
                            }
                        }""")
                    sleep(800)
                    for _ in range(10):
                        body2 = page.evaluate('document.body.innerText')
                        if "保存" in body2 and '跳过' not in body2:
                            break
                        sleep(200)
                    continue

                # 路径B: 保存按钮
                if "保存" in body:
                    save = page.locator('.t-dialog__footer button:has-text("保存")')
                    if save.count() > 0 and save.first.is_visible():
                        save.first.click()
                        saved_publish = True
                        sleep(800)
                        break

                sleep(200)

            # 从 remaining 中移除本轮已发布的ID
            remaining -= set(visible_ids)
            sleep(800)  # 等页面刷新，后续页填充到第1页

        print(f"[3/4] 勾选+发布: {total_checked} 件", flush=True)
        saved = saved_publish
    else:
        # 全选
        checked = 0
        total_pages = page.evaluate("""() => {
            var pages = document.querySelectorAll('.t-pagination__number');
            return pages.length ? Math.max(...Array.from(pages).map(p=>parseInt(p.textContent)).filter(n=>!isNaN(n)),1) : 1;
        }""")
        for pg in range(1, total_pages + 1):
            if pg > 1:
                page.evaluate("""(n) => {
                    var pages = document.querySelectorAll('.t-pagination__number');
                    for(var p of pages){if(parseInt(p.textContent)===n){p.click();return;}}
                }""", pg)
                sleep(1000)
            cnt = page.evaluate("""(tablerow) => {
                var rows = document.querySelectorAll(tablerow);
                var n = 0;
                for(var i=0;i<rows.length;i++) {
                    if(rows[i].textContent.length < 30) continue;
                    var cb = rows[i].querySelector('input[type="checkbox"]');
                    if(cb && !cb.checked){cb.click();n++;}
                }
                return n;
            }""", SEL.TABLE_ROW)
            checked += cnt
        print(f"[3/4] 全选: {checked} 件", flush=True)

        sleep(200)
        print(f"[3/4] 全选: {checked} 件", flush=True)

        # 全选路径 → 旧版发布流程
        page.locator(f'button:has-text("{TXT.BTN_PUBLISH}")').first.hover()
        sleep(200)
        page.locator(f'button:has-text("{TXT.BTN_PUBLISH}")').first.click()
        sleep(800)
        page.locator('.t-dropdown__item-text').filter(has_text="立即发布").first.click()
        print("[4/4] 已点立即发布", flush=True)

        # 处理弹窗（两种路径）
        saved = False
        for _ in range(20):
            body = page.evaluate('document.body.innerText')
            if ('跳过未设置类目产品并继续发布' in body or '璺宠繃鏈缃被鐩骇' in body):
                print("  弹窗A: 未设置类目，点击跳过", flush=True)
                try:
                    page.locator('text=跳过未设置类目产品并继续发布').first.click(timeout=T.ELEMENT_VISIBLE)
                except:
                    page.evaluate("""() => {
                        const btns = document.querySelectorAll('[class*="dialog"] button, [class*="dialog"] span');
                        for (const btn of btns) {
                            if (btn.textContent.includes('跳过') || btn.textContent.includes('璺宠繃')) {
                                btn.click(); return;
                            }
                        }
                    }""")
                sleep(800)
                for _ in range(10):
                    body2 = page.evaluate('document.body.innerText')
                    if "保存" in body2 and '跳过' not in body2:
                        break
                    sleep(200)
                continue
            if "保存" in body:
                save = page.locator('.t-dialog__footer button:has-text("保存")')
                if save.count() > 0 and save.first.is_visible():
                    save.first.click()
                    print("  ✅ 保存", flush=True)
                    saved = True
                    sleep(800)
                    break
            sleep(200)

        if not saved:
            print("  ⚠️ 未找到保存按钮", flush=True)

    # 验证阶段
    try:
        body_now = page.evaluate('document.body.innerText')
        draft_cnt = re.findall(r'草稿箱[（(](\d+)[）)]', body_now)
        pending_cnt = re.findall(r'发布中[（(](\d+)[）)]', body_now)
        print(f"  草稿箱: {draft_cnt[0] if draft_cnt else '?'}")
        print(f"  发布中: {pending_cnt[0] if pending_cnt else '?'}")

        check_ids = target_ids if target_ids else []
        if check_ids:
            found = sum(1 for pid in check_ids if pid in body_now)
            print(f"  发布确认: {found}/{len(check_ids)} 在发布中", flush=True)
            if found < len(check_ids):
                page.locator('text=草稿箱').first.click()
                sleep(800)
                body_draft = page.evaluate('document.body.innerText')
                missing = [pid for pid in check_ids if pid not in body_now and pid in body_draft]
                if missing:
                    print(f"  ⚠️ {len(missing)}件还在草稿箱（可能发布异步中）: {missing}")
    except Exception as e:
        print(f"  验证异常: {e}", flush=True)

    print("=" * 60)
    print("  ✅ 发布完成!" if saved else "  ⚠️ 发布可能未完成")
    print("=" * 60)

    p.stop()
    return 0 if saved else 1

if __name__ == "__main__":
    sys.exit(main())
