#!/usr/bin/env python3
import sys, json, time
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
    print('NO_PUBLISH_TAB')
    p.stop()
    exit()

# 草稿箱
page.locator('text=草稿箱').first.click()
time.sleep(1.5)

# 选顺顺
tags = page.locator('.t-tag--check')
for i in range(tags.count()):
    if '順順' in tags.nth(i).text_content():
        tags.nth(i).click()
        break
time.sleep(0.5)

# 搜断布机
page.locator('input').first.fill('断布机')
time.sleep(0.5)
page.locator('button:has-text("查询")').first.click()
time.sleep(3)

# 只勾断布机
page.evaluate("""() => {
    document.querySelectorAll('input[type="checkbox"]').forEach(cb => { if(cb.checked) cb.click(); });
    var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
    rows.forEach(function(row) {
        if(row.textContent.includes('626005526840')) {
            var cb = row.querySelector('input[type="checkbox"]');
            if(cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles:true})); }
        }
    });
}""")
time.sleep(0.5)

# 产品发布
page.locator('button:has-text("产品发布")').first.click(force=True)
time.sleep(2)

# 立即发布
page.locator('.t-dropdown__item-text:text("立即发布")').first.click(timeout=5000)
time.sleep(3)

# 弹窗处理
for loop in range(15):
    info = page.evaluate("""() => {
        var ds = document.querySelectorAll('[class*="dialog"]');
        for(var i=0;i<ds.length;i++) {
            if(!ds[i].offsetParent) continue;
            var btns = [];
            ds[i].querySelectorAll('button').forEach(function(b){if(b.offsetParent) btns.push(b.textContent.trim());});
            return JSON.stringify({text: ds[i].textContent.substring(0,200), btns: btns});
        }
        return null;
    }""")
    if not info:
        print('No dialog')
        break
    info = json.loads(info)
    print(f'Dialog: {info["text"][:60]} btns: {info["btns"]}')
    clicked = False
    for b in info['btns']:
        if '保存' in b:
            page.evaluate('() => { document.querySelectorAll("[class*=dialog] button").forEach(function(x){if(x.offsetParent && x.textContent.trim()=="' + b + '") x.click();}); }')
            print(f'  -> {b}')
            clicked = True
            break
    if not clicked:
        for b in info['btns']:
            if '跳过' in b or '继续' in b:
                page.evaluate('() => { document.querySelectorAll("[class*=dialog] button").forEach(function(x){if(x.offsetParent && x.textContent.trim()=="' + b + '") x.click();}); }')
                print(f'  -> {b}')
                clicked = True
                break
    if not clicked and ('确认' in info['btns'] or '确定' in info['btns']):
        for b in info['btns']:
            if b in ('确认','确定'):
                page.evaluate('() => { document.querySelectorAll("[class*=dialog] button").forEach(function(x){if(x.offsetParent && x.textContent.trim()=="' + b + '") x.click();}); }')
                print(f'  -> {b}')
                clicked = True
                break
    if not clicked:
        break
    time.sleep(2)

print('DONE')
page.close(); b.close(); p.stop()
