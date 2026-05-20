#!/usr/bin/env python3
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start(); b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
page = b.contexts[0].pages[0]
page.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=20000)
page.wait_for_timeout(2000)
page.locator('text=草稿箱').first.click(); page.wait_for_timeout(2000)
tags = page.locator('.t-tag--check')
for i in range(tags.count()):
    if '順順' in tags.nth(i).text_content(): tags.nth(i).click(); break
page.wait_for_timeout(500)
page.locator('button:has-text("查询")').first.click(); page.wait_for_timeout(4000)
page.locator('input').first.fill('锅巴'); page.wait_for_timeout(500)
page.locator('button:has-text("查询")').first.click(); page.wait_for_timeout(3000)
page.evaluate("() => { document.querySelectorAll('input[type=\"checkbox\"]').forEach(cb => {if(cb.checked) cb.click();}); }")
page.wait_for_timeout(300)
page.evaluate("""() => {
    var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
    for(var i=0;i<rows.length;i++) {
        if(rows[i].textContent.includes('768896253679')) {
            var cb = rows[i].querySelector('input[type="checkbox"]');
            if(cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles:true})); }
        }
    }
}""")
page.wait_for_timeout(500)
page.locator('button:has-text("产品发布")').first.hover(); page.wait_for_timeout(500)
page.locator('button:has-text("产品发布")').first.click(); page.wait_for_timeout(1500)
page.locator('.t-dropdown__item-text').filter(has_text='立即发布').first.click()
# 等3秒再查
page.wait_for_timeout(3000)
result = page.evaluate("""() => {
    var all = document.querySelectorAll('*');
    var found = [];
    for(var i=0;i<all.length;i++) {
        var cls = (all[i].className || '') + ' ' + (all[i].id || '');
        if(cls.includes('t-dialog')) {
            var rect = all[i].getBoundingClientRect();
            if(rect.width > 5 && rect.height > 5) {
                var btns = [];
                all[i].querySelectorAll('button').forEach(function(b){if(b.offsetParent) btns.push(b.textContent.trim());});
                found.push({cls: cls.substring(0,60), btns: btns});
            }
        }
    }
    return JSON.stringify(found);
}""")
parsed = json.loads(result)
print(f'After 3s: {len(parsed)} elements', flush=True)
for d in parsed:
    print(f'  cls={d[\"cls\"]} btns={d[\"btns\"]}', flush=True)
p.stop()
