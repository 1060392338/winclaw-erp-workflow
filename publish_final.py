#!/usr/bin/env python3
import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
page = b.contexts[0].pages[0]

# 导航到发布页  
page.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=20000)
time.sleep(3)
print('1. GOTO', flush=True)

page.locator('text=草稿箱').first.click()
time.sleep(2)
print('2. DRAFT', flush=True)

tags = page.locator('.t-tag--check')
for i in range(tags.count()):
    if '順順' in tags.nth(i).text_content():
        tags.nth(i).click()
        break
time.sleep(0.5)

page.locator('button:has-text("查询")').first.click()
time.sleep(4)
print('3. QUERIED', flush=True)

# 取消所有
page.evaluate("() => { document.querySelectorAll('input[type=\"checkbox\"]').forEach(cb => {if(cb.checked) cb.click();}); }")
time.sleep(0.3)

# 勾选4个
ids = ['1029997937003','1018247628403','976662858715','1011221892271']
for pid in ids:
    page.evaluate("""(pid) => {
        var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
        for(var i=0;i<rows.length;i++) {
            if(rows[i].textContent.includes(pid)) {
                var cb = rows[i].querySelector('input[type="checkbox"]');
                if(cb) { cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true})); }
            }
        }
    }""", pid)
time.sleep(0.5)
print('4. CHECKED', flush=True)

# 产品发布
page.locator('button:has-text("产品发布")').first.hover()
time.sleep(0.5)
page.locator('button:has-text("产品发布")').first.click()
time.sleep(2)
print('5. PUBLISHED', flush=True)

# 立即发布
page.locator('.t-dropdown__item-text').filter(has_text='立即发布').first.click()
print('6. CLICKED_INSTANT', flush=True)

# 找保存
for _ in range(30):
    try:
        save = page.locator('.t-dialog__footer button:has-text("保存")')
        if save.count() > 0 and save.first.is_visible():
            save.first.click()
            print('7. SAVE_CLICKED', flush=True)
            time.sleep(2)
            break
    except:
        pass
    time.sleep(0.3)
else:
    print('7. SAVE_NOT_FOUND', flush=True)

# 切发布中
try:
    page.locator('text=发布中').first.click()
    time.sleep(2)
    body = page.evaluate('document.body.innerText')
    for pid in ids:
        if pid in body:
            print(f'  {pid}: OK', flush=True)
        else:
            print(f'  {pid}: NO', flush=True)
except Exception as e:
    print(f'PUB_TAB: {e}', flush=True)

print('DONE', flush=True)
p.stop()
