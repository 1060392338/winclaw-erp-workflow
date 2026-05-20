#!/usr/bin/env python3
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
from infrastructure.config_loader import ConfigLoader
from playwright.sync_api import sync_playwright
_cfg = ConfigLoader().load()
port = _cfg.erp_cdp_ports[0]
p = sync_playwright().start()
b = p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
page = b.new_page()

# go to publish page
page.goto(f'{_cfg.erp_url}/member/product/shopee/publish', wait_until='networkidle', timeout=20000)
page.wait_for_timeout(2000)

# close dialogs
page.evaluate("() => { document.querySelectorAll('[class*=\"dialog\"]').forEach(d => { d.style.display='none'; }); }")
page.wait_for_timeout(500)

# click 草稿箱
try:
    page.locator('text=草稿箱').first.click()
    page.wait_for_timeout(2000)
except:
    pass

# select store
try:
    stores = page.locator('.t-tag--check')
    s = stores.count()
    for i in range(s):
        name = stores.nth(i).text_content()
        if '順順' in name:
            stores.nth(i).click()
            break
    page.wait_for_timeout(500)
    page.locator('button:has-text("查询")').first.click()
    page.wait_for_timeout(4000)
except Exception as e:
    print(f'Store filter error: {e}')

# check all checkbox
page.evaluate("() => { document.querySelectorAll('input[type=\"checkbox\"]').forEach(cb => { if(!cb.checked) cb.click(); }); }")
page.wait_for_timeout(500)

# click 产品发布 button
page.locator('button:has-text("产品发布")').first.click(force=True)
page.wait_for_timeout(1500)

# click 立即发布 in dropdown
try:
    page.locator('.t-dropdown__item-text:text("立即发布")').first.click(timeout=5000)
    print('Clicked: 立即发布')
except Exception as e:
    print(f'Dropdown error: {e}')

page.wait_for_timeout(3000)

# inspect the dialog
dlg = page.evaluate("""() => {
    var ds = document.querySelectorAll('[class*=\"dialog\"]');
    var result = [];
    for (var i = 0; i < ds.length; i++) {
        if (!ds[i].offsetParent) continue;
        var html = ds[i].innerHTML.substring(0, 2000);
        var text = ds[i].textContent.substring(0, 500);
        var btns = [];
        ds[i].querySelectorAll('button').forEach(function(b) {
            if(b.offsetParent) btns.push({text: b.textContent.trim(), class: b.className.substring(0,100)});
        });
        result.push({html: html, text: text, buttons: btns});
    }
    return JSON.stringify(result, null, 2);
}""")
print(f'Dialog info:\n{dlg[:3000]}')

page.close(); b.close(); p.stop()
