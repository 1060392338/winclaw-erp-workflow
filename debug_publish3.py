#!/usr/bin/env python3
"""Debug: exactly simulate run_publish.py flow to see if dialog appears"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')

page = b.contexts[0].pages[0]

# Step 1: navigate to publish
page.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=20000)
print('1. Navigated', flush=True)
page.wait_for_timeout(2000)

# Step 2: close dialogs
page.evaluate("() => { document.querySelectorAll('[class*=\"dialog\"]').forEach(d => { d.style.display='none'; }); }")
print('2. Dialogs closed', flush=True)

# Step 3: click 草稿箱 tab
page.locator('text=草稿箱').first.click()
page.wait_for_timeout(2000)
print('3. Clicked 草稿箱', flush=True)

# Step 4: select store
tags = page.locator('.t-tag--check')
for i in range(tags.count()):
    if '順順' in tags.nth(i).text_content():
        tags.nth(i).click()
        break
page.wait_for_timeout(500)
print('4. Selected store', flush=True)

# Step 5: query
page.locator('button:has-text("查询")').first.click()
page.wait_for_timeout(4000)
print('5. Queried', flush=True)

# Step 6: search for the product by main货号
page.locator('input').first.fill('768896253679')
page.wait_for_timeout(500)
page.locator('button:has-text("查询")').first.click()
page.wait_for_timeout(3000)
print('6. Searched', flush=True)

# Step 7: check if checkbox is visible 
checkboxes = page.locator('input[type="checkbox"]')
print(f'7. Checkboxes: {checkboxes.count()}', flush=True)

# Check if the product is found
found = page.locator('text=768896253679').count()
print(f'   Found product: {found}', flush=True)

if found > 0:
    # Try to check it
    cb = page.locator('text=768896253679').first
    # click the checkbox row
    page.evaluate("""() => {
        var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
        for(var i=0;i<rows.length;i++) {
            if(rows[i].textContent.includes('768896253679')) {
                var cb = rows[i].querySelector('input[type="checkbox"]');
                if(cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles: true})); return 'checked'; }
            }
        }
        return 'not found';
    }""")
    page.wait_for_timeout(500)
    print('7b. Checkbox checked', flush=True)

    # Step 8: click 产品发布
    page.locator('button:has-text("产品发布")').first.hover()
    page.wait_for_timeout(500)
    page.locator('button:has-text("产品发布")').first.click()
    page.wait_for_timeout(2000)
    print('8. Clicked 产品发布', flush=True)

    # Check dropdown
    dd = page.locator('.t-dropdown__item-text')
    print(f'   Dropdown count: {dd.count()}', flush=True)
    for i in range(dd.count()):
        print(f'   [{i}] {dd.nth(i).text_content()}', flush=True)

    if dd.count() > 0:
        # Click 立即发布
        dd.filter(has_text='立即发布').first.click()
        print('9. Clicked 立即发布', flush=True)
        page.wait_for_timeout(3000)

        # Check for dialog
        for _ in range(20):
            page.wait_for_timeout(500)
            info = page.evaluate("""() => {
                var ds = document.querySelectorAll('[class*="dialog"]');
                for(var i=0;i<ds.length;i++) {
                    if(!ds[i].offsetParent) continue;
                    var btns = [];
                    ds[i].querySelectorAll('button').forEach(function(b){if(b.offsetParent) btns.push(b.textContent.trim());});
                    return JSON.stringify({text: ds[i].textContent.substring(0,300), btns: btns});
                }
                return null;
            }""")
            if info:
                info = json.loads(info)
                print(f'10. Dialog: {info["text"][:60]} btns: {info["btns"]}', flush=True)
                # Click save
                for b in info['btns']:
                    if '保存' in b:
                        page.evaluate(f"() => {{ document.querySelectorAll('[class*=dialog] button').forEach(function(x){{ if(x.offsetParent && x.textContent.trim()=='{b}') x.click(); }}); }}")
                        print(f'11. Clicked: {b}', flush=True)
                        page.wait_for_timeout(2000)
                        break
                break
        else:
            print('10. No dialog found after 10s', flush=True)

p.stop()
