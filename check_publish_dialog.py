#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
# 复用已有tab
page = None
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url:
            page = pg
            break
if not page:
    print('No publish tab')
    p.stop()
    exit()

# 切草稿箱tab
try:
    page.locator('text=草稿箱').first.click()
    page.wait_for_timeout(2000)
except:
    pass

# 选顺顺店铺标签
try:
    tags = page.locator('.t-tag--check')
    for i in range(tags.count()):
        if '順順' in tags.nth(i).text_content():
            tags.nth(i).click()
            break
    page.wait_for_timeout(500)
    page.locator('button:has-text("查询")').first.click()
    page.wait_for_timeout(4000)
except Exception as e:
    print(f'Filter: {e}')

# 勾选所有
page.evaluate("() => { document.querySelectorAll('input[type=\"checkbox\"]').forEach(cb => { if(!cb.checked) cb.click(); }); }")
page.wait_for_timeout(500)

# 点产品发布
page.locator('button:has-text("产品发布")').first.click(force=True)
page.wait_for_timeout(1500)

# 检查是否有下拉菜单
dd = page.locator('.t-dropdown__item-text:text("立即发布")')
print(f'Dropdown: visible={dd.first.is_visible()}, count={dd.count()}')

# 点立即发布
if dd.count() > 0:
    dd.first.click(timeout=5000)
    page.wait_for_timeout(3000)
    
    # 检查弹窗
    dlg_info = page.evaluate("""() => {
        var ds = document.querySelectorAll('[class*=\"dialog\"]');
        var r = [];
        for (var i = 0; i < ds.length; i++) {
            if(!ds[i].offsetParent) continue;
            var btns = [];
            ds[i].querySelectorAll('button').forEach(function(b){
                if(b.offsetParent) btns.push({t: b.textContent.trim(), c: b.className.substring(0,60)});
            });
            r.push({text: ds[i].textContent.substring(0,200), btns: btns});
        }
        return JSON.stringify(r, null, 2);
    }""")
    print(f'Dialogs after click:')
    print(dlg_info[:3000])
else:
    print('No dropdown - check if product released directly')

page.close()
p.stop()
