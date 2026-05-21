#!/usr/bin/env python3
"""
直接发布 — 基于 publish_final.py 成功经验
用 locator API 检测弹窗保存按钮，不依赖 JS evaluate。

用法:
    python publish_direct.py "順順の小屋童裝（本土）" --products id1,id2
    python publish_direct.py "順順の小屋童裝（本土）" --all
"""
import sys, time, re, argparse
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
        page2.goto(f"{_cfg2.erp_url}/member/product/shopee/publish", wait_until="networkidle", timeout=30000)
        time.sleep(5)

        # 选店铺
        if store:
            tags2 = page2.locator('.t-tag--check')
            for i in range(tags2.count()):
                txt = tags2.nth(i).text_content()
                if txt == store:
                    tags2.nth(i).click()
                    break
            time.sleep(0.5)
            page2.locator('button:has-text("查询")').first.click()
            time.sleep(3)

        # 逐tab查找：只看发布中/发布成功/发布失败（不看草稿箱）
        found = False
        for tab_text in ['发布中', '发布成功', '发布失败']:
            tab = page2.locator(f'text={tab_text}').first
            if tab.count() > 0:
                tab.click()
                time.sleep(2)
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
    page.goto(f"{_cfg.erp_url}/member/product/shopee/publish", wait_until="networkidle", timeout=30000)
    time.sleep(5)  # 关键：等足5秒确保弹窗组件就绪
    print("[1/4] 导航完成", flush=True)

    # 切草稿箱
    page.locator('text=草稿箱').first.click()
    time.sleep(2)
    print("[2/4] 草稿箱", flush=True)

    # 选店铺 — 精确匹配完整店名
    # 页面结构：标签分多组（地区/店铺/商户），店铺标签包含完整店名
    # 先取消所有已选店铺标签，再点击目标店铺
    tags = page.locator('.t-tag--check')
    target_clicked = False
    for i in range(tags.count()):
        txt = tags.nth(i).text_content()
        if txt == store:
            # 如果已选中，跳过；否则点它
            cls = tags.nth(i).get_attribute('class') or ''
            if 't-tag--checked' not in cls:
                tags.nth(i).click()
                print(f"  选中店铺: {txt}", flush=True)
            else:
                print(f"  店铺已选中: {txt}", flush=True)
            target_clicked = True
        else:
            # 如果是其他店铺标签且已选中，取消选中
            cls = tags.nth(i).get_attribute('class') or ''
            if 't-tag--checked' in cls and '全部' not in txt and '台湾' not in txt:
                tags.nth(i).click()
    if not target_clicked:
        print(f"  ⚠️ 未找到店铺 [{store}]，尝试模糊匹配", flush=True)
        for i in range(tags.count()):
            txt = tags.nth(i).text_content()
            if store.replace('（本土）','') in txt or store.replace('(本土)','') in txt:
                tags.nth(i).click()
                print(f"  模糊匹配选中: {txt}", flush=True)
                target_clicked = True
                break
    time.sleep(0.5)
    page.locator('button:has-text("查询")').first.click()
    time.sleep(4)

    if target_ids:
        # 按ID匹配勾选 — 取消全部、只勾指定ID（支持翻页）
        page.evaluate("() => { document.querySelectorAll('input[type=\"checkbox\"]').forEach(cb => {if(cb.checked) cb.click();}); }")
        time.sleep(0.3)
        total_pages = page.evaluate("""() => {
            var pages = document.querySelectorAll('.t-pagination__number');
            return pages.length ? Math.max(...Array.from(pages).map(p=>parseInt(p.textContent)).filter(n=>!isNaN(n)),1) : 1;
        }""")
        checked = 0
        for pg in range(1, total_pages + 1):
            if pg > 1:
                page.evaluate("""(n) => {
                    var pages = document.querySelectorAll('.t-pagination__number');
                    for(var p of pages){if(parseInt(p.textContent)===n){p.click();return;}}
                }""", pg)
                time.sleep(3)
            for pid in target_ids:
                c = page.evaluate("""(pid) => {
                    var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
                    for(var i=0;i<rows.length;i++) {
                        if(rows[i].textContent.includes(pid)) {
                            var cb = rows[i].querySelector('input[type="checkbox"]');
                            if(cb && !cb.checked) { cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true})); return 1; }
                        }
                    }
                    return 0;
                }""", pid)
                checked += c
                time.sleep(0.1)
        print(f"[3/4] 勾选: {checked} 件", flush=True)
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
                time.sleep(3)
            cnt = page.evaluate("""() => {
                var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
                var n = 0;
                for(var i=0;i<rows.length;i++) {
                    if(rows[i].textContent.length < 30) continue;
                    var cb = rows[i].querySelector('input[type="checkbox"]');
                    if(cb && !cb.checked){cb.click();n++;}
                }
                return n;
            }""")
            checked += cnt
        print(f"[3/4] 全选: {checked} 件", flush=True)

    time.sleep(0.5)

    # 产品发布 hover+click
    page.locator('button:has-text("产品发布")').first.hover()
    time.sleep(0.5)
    page.locator('button:has-text("产品发布")').first.click()
    time.sleep(2)

    # 立即发布
    page.locator('.t-dropdown__item-text').filter(has_text='立即发布').first.click()
    print("[4/4] 已点立即发布", flush=True)

    # 处理弹窗（两种路径）
    saved = False
    for _ in range(20):
        body = page.evaluate('document.body.innerText')
        
        # 路径A: 「未设置类目」弹窗 → 跳过 → 等弹窗变保存
        if ('跳过未设置类目产品并继续发布' in body or '璺宠繃鏈缃被鐩骇' in body):
            print("  弹窗A: 未设置类目，点击跳过", flush=True)
            try:
                page.locator('text=跳过未设置类目产品并继续发布').first.click(timeout=3000)
            except:
                # 编码损坏时用 JS 兜底
                page.evaluate("""() => {
                    const btns = document.querySelectorAll('[class*="dialog"] button, [class*="dialog"] span');
                    for (const btn of btns) {
                        if (btn.textContent.includes('跳过') || btn.textContent.includes('璺宠繃')) {
                            btn.click(); return;
                        }
                    }
                }""")
            time.sleep(2)
            # 等弹窗从「跳过」变成「保存」
            for _ in range(10):
                body2 = page.evaluate('document.body.innerText')
                if '保存' in body2 and '跳过' not in body2:
                    break
                time.sleep(0.5)
            continue
        
        # 路径B: 点击「产品发布」后的确认弹窗 → 保存
        if '保存' in body:
            save = page.locator('.t-dialog__footer button:has-text("保存")')
            if save.count() > 0 and save.first.is_visible():
                save.first.click()
                print("  ✅ 保存", flush=True)
                saved = True
                time.sleep(2)
                break
        
        time.sleep(0.5)
    
    if not saved:
        print("  ⚠️ 未找到保存按钮", flush=True)

    # 验证阶段：分别读取各 tab 计数
    try:
        # 先读草稿箱 tab 计数（当前在发布中tab，但 DOM 里 tab 文本还在）
        body_now = page.evaluate('document.body.innerText')
        draft_cnt = re.findall(r'草稿箱[（(](\d+)[）)]', body_now)
        pending_cnt = re.findall(r'发布中[（(](\d+)[）)]', body_now)
        print(f"  草稿箱: {draft_cnt[0] if draft_cnt else '?'}")
        print(f"  发布中: {pending_cnt[0] if pending_cnt else '?'}")

        if target_ids:
            # 在发布中 tab 内搜索目标主货号
            found = sum(1 for pid in target_ids if pid in body_now)
            print(f"  发布确认: {found}/{len(target_ids)} 在发布中", flush=True)
            if found < len(target_ids):
                # 可能有部分商品还没刷到发布中，切回草稿箱验证
                page.locator('text=草稿箱').first.click()
                time.sleep(2)
                body_draft = page.evaluate('document.body.innerText')
                missing = [pid for pid in target_ids if pid not in body_now and pid in body_draft]
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
