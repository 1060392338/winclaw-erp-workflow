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
    if args.check_product:
        check_pid = args.check_product
        _cfg2 = ConfigLoader().load()
        port2 = _cfg2.erp_cdp_ports[0]
        p2 = sync_playwright().start()
        b2 = p2.chromium.connect_over_cdp(f"http://127.0.0.1:{port2}")
        page2 = b2.contexts[0].pages[0]
        page2.goto(f"{_cfg2.erp_url}/member/product/shopee/publish", wait_until="networkidle", timeout=30000)
        time.sleep(5)
        body2 = page2.evaluate('document.body.innerText')
        found = check_pid in body2
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

    # 选店铺
    tags = page.locator('.t-tag--check')
    for i in range(tags.count()):
        if store[:4] in tags.nth(i).text_content():
            tags.nth(i).click()
            break
    time.sleep(0.5)
    page.locator('button:has-text("查询")').first.click()
    time.sleep(4)

    if target_ids:
        # 按ID匹配勾选 — 取消全部、只勾指定ID
        page.evaluate("() => { document.querySelectorAll('input[type=\"checkbox\"]').forEach(cb => {if(cb.checked) cb.click();}); }")
        time.sleep(0.3)
        for pid in target_ids:
            page.evaluate("""(pid) => {
                var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
                for(var i=0;i<rows.length;i++) {
                    if(rows[i].textContent.includes(pid)) {
                        var cb = rows[i].querySelector('input[type="checkbox"]');
                        if(cb) { cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true})); }
                    }
                }
            }""", pid)
            time.sleep(0.1)
        print(f"[3/4] 勾选: {len(target_ids)} 件", flush=True)
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
        
        # 路径A: 「未设置类目」弹窗 → 跳过
        if '跳过未设置类目产品并继续发布' in body:
            print("  弹窗A: 未设置类目，点击跳过", flush=True)
            page.locator('text=跳过未设置类目产品并继续发布').first.click()
            time.sleep(1.5)
            # 跳过后页面回到初始状态，需要重新点「产品发布」→「立即发布」
            page.locator('button:has-text("产品发布")').first.hover()
            time.sleep(0.3)
            page.locator('button:has-text("产品发布")').first.click()
            time.sleep(1)
            page.locator('.t-dropdown__item-text').filter(has_text='立即发布').first.click()
            print("  弹窗A: 重新点击立即发布", flush=True)
            time.sleep(1)
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
