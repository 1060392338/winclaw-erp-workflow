#!/usr/bin/env python3
import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
page = b.contexts[0].pages[0]

page.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=20000)
page.wait_for_timeout(2000)
# 跳过关弹窗
page.locator('text=草稿箱').first.click(); page.wait_for_timeout(2000)
tags = page.locator('.t-tag--check')
for i in range(tags.count()):
    if '順順' in tags.nth(i).text_content(): tags.nth(i).click(); break
page.wait_for_timeout(500)
page.locator('button:has-text("查询")').first.click(); page.wait_for_timeout(4000)
page.locator('input').first.fill('锅巴'); page.wait_for_timeout(500)
page.locator('button:has-text("查询")').first.click(); page.wait_for_timeout(3000)
# uncheck all, check only 锅巴
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
# 产品发布 hover+click
page.locator('button:has-text("产品发布")').first.hover(); page.wait_for_timeout(500)
page.locator('button:has-text("产品发布")').first.click(); page.wait_for_timeout(1500)
page.locator('.t-dropdown__item-text').filter(has_text='立即发布').first.click()
# 立即检查弹窗，不等3秒
page.wait_for_timeout(500)
result = page.evaluate("""() => {
    var all = document.querySelectorAll('*');
    var found = [];
    for(var i=0;i<all.length;i++) {
        var cls = (all[i].className || '') + ' ' + (all[i].id || '');
        if(cls.includes('dialog') || cls.includes('modal') || cls.includes('overlay') || cls.includes('mask') || cls.includes('popup')) {
            var rect = all[i].getBoundingClientRect();
            if(rect.width > 5 && rect.height > 5) {
                var btns = [];
                all[i].querySelectorAll('button').forEach(function(b){if(b.offsetParent || b.getBoundingClientRect().width > 0) btns.push(b.textContent.trim());});
                found.push({
                    tag: all[i].tagName,
                    cls: cls.substring(0,60),
                    rect: Math.round(rect.width)+'x'+Math.round(rect.height),
                    text: all[i].textContent.substring(0,100).replace(/\\n/g,' '),
                    btns: btns
                });
            }
        }
    }
    return JSON.stringify(found);
}""")
parsed = json.loads(result)
print('Immediately after click:', flush=True)
for d in parsed:
    print('  class=' + d['cls'][:50], 'rect=' + d['rect'], 'btns=' + str(d['btns']), 'text=' + d['text'][:60], flush=True)
if not parsed:
    print('  NONE', flush=True)
# Also check if save button is somewhere
save = page.locator('button:has-text("保存")')
print(f'Save button: count={save.count()}, visible={save.first.is_visible() if save.count()>0 else "N/A"}', flush=True)
p.stop()
