#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
page = None
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url:
            page = pg
            break
if not page:
    print('No publish tab')
    p.stop(); exit()

# 切草稿箱、选店铺、查
page.locator('text=草稿箱').first.click()
page.wait_for_timeout(2000)
tags = page.locator('.t-tag--check')
for i in range(tags.count()):
    if '順順' in tags.nth(i).text_content():
        tags.nth(i).click()
        break
page.wait_for_timeout(500)
page.locator('button:has-text("查询")').first.click()
page.wait_for_timeout(4000)

# 只勾选断布机
page.evaluate("""() => {
    var rows = document.querySelectorAll('[class*=\"virtual-table-tr\"]');
    rows.forEach(function(row) {
        var t = row.textContent;
        if(t.includes('626005526840')) {
            var cb = row.querySelector('input[type=\"checkbox\"]');
            if(cb && !cb.checked) cb.click();
        } else {
            var cb = row.querySelector('input[type=\"checkbox\"]');
            if(cb && cb.checked) cb.click();
        }
    });
}""")
page.wait_for_timeout(500)

# 点产品发布
page.locator('button:has-text("产品发布")').first.click(force=True)
page.wait_for_timeout(1500)

# 检查下拉
dd = page.locator('.t-dropdown__item-text')
print(f'Dropdown items count: {dd.count()}')
for i in range(dd.count()):
    print(f'  [{i}] {dd.nth(i).text_content()}')

# 看弹窗
for _ in range(5):
    page.wait_for_timeout(1000)
    info = page.evaluate("""() => {
        var ds = document.querySelectorAll('[class*=\"dialog\"]');
        for(var i=0;i<ds.length;i++) {
            if(ds[i].offsetParent) return {text: ds[i].textContent.substring(0,200), html: ds[i].innerHTML.substring(0,500)};
        }
        return null;
    }""")
    if info:
        print(f'Dialog: {info}')
        break

page.close(); p.stop()
