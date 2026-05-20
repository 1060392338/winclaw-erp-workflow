#!/usr/bin/env python3
import sys, re
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
if page:
    body = page.evaluate('document.body.innerText')
    draft = re.findall(r'草稿箱[（(](\d+)[）)]', body)
    pending = re.findall(r'发布中[（(](\d+)[）)]', body)
    print(f'草稿箱: {draft[0] if draft else "?"}')
    print(f'发布中: {pending[0] if pending else "?"}')
    # 切发布中看有没有
    try:
        page.locator('text=发布中').first.click()
        page.wait_for_timeout(2000)
        body2 = page.evaluate('document.body.innerText')
        if '626005526840' in body2 or '断布机' in body2:
            print('断布机在发布中 ✅')
        else:
            print('断布机不在发布中')
    except:
        pass
else:
    print('No publish tab')
p.stop()
