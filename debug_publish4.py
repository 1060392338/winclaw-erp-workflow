#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
page = b.contexts[0].pages[0]

page.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=20000)
page.wait_for_timeout(2000)
page.evaluate("() => { document.querySelectorAll('[class*=\"dialog\"]').forEach(d => d.style.display='none'); }")

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

# search 锅巴
page.locator('input').first.fill('锅巴')
page.wait_for_timeout(500)
page.locator('button:has-text("查询")').first.click()
page.wait_for_timeout(3000)

# check only 锅巴
page.evaluate("""() => {
    var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
    for(var i=0;i<rows.length;i++) {
        if(rows[i].textContent.includes('768896253679')) {
            var cb = rows[i].querySelector('input[type="checkbox"]');
            if(cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles:true})); return; }
        }
    }
}""")
page.wait_for_timeout(500)

# 产品发布 hover+click
page.locator('button:has-text("产品发布")').first.hover()
page.wait_for_timeout(500)
page.locator('button:has-text("产品发布")').first.click()
page.wait_for_timeout(1500)

# 立即发布
page.locator('.t-dropdown__item-text').filter(has_text='立即发布').first.click()
page.wait_for_timeout(3000)

# 等弹窗
for _ in range(20):
    page.wait_for_timeout(500)
    dlg = page.evaluate("""() => {
        var ds = document.querySelectorAll('[class*="dialog"]');
        for(var i=0;i<ds.length;i++) {
            if(!ds[i].offsetParent) continue;
            return ds[i].textContent.substring(0,200);
        }
        return null;
    }""")
    if dlg:
        print(f'DIALOG: {dlg}', flush=True)
        break
else:
    print('NO_DIALOG', flush=True)

# 切发布中
try:
    page.locator('text=发布中').first.click()
    page.wait_for_timeout(2000)
    body = page.evaluate('document.body.innerText')
    if '768896253679' in body:
        print('IN_PUBLISHING=Y', flush=True)
    else:
        print('IN_PUBLISHING=N', flush=True)
except Exception as e:
    print(f'PUBLISHING_TAB: {e}', flush=True)

p.stop()
