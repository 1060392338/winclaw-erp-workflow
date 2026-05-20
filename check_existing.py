#!/usr/bin/env python3
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
# 复用已有采集箱tab
page = None
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url:
            page = pg
            break
if not page:
    print('No publish tab found, using collect-box tab')
    for ctx in b.contexts:
        for pg in ctx.pages:
            if 'collect-box' in pg.url:
                # 导航到发布页
                pg.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=20000)
                page = pg
                break
if page:
    body = page.evaluate('document.body.innerText')
    print('TEXT:', body[:300].replace('\n',' | '))
    draft = re.findall(r'草稿箱[（(](\d+)[）)]', body)
    pending = re.findall(r'发布中[（(](\d+)[）)]', body)
    success = re.findall(r'发布成功[（(](\d+)[）)]', body)
    print(f'草稿箱: {draft[0] if draft else "?"}')
    print(f'发布中: {pending[0] if pending else "?"}')
    print(f'发布成功: {success[0] if success else "?"}')
    # 搜索断布机
    try:
        page.locator('input').first.fill('断布机')
        page.wait_for_timeout(500)
        page.locator('button:has-text("查询")').first.click()
        page.wait_for_timeout(3000)
        cnt = page.locator('text=626005526840').count()
        print(f'断布机626005526840: {"找到" if cnt > 0 else "未找到"}')
    except Exception as e:
        print(f'Search error: {e}')
else:
    print('No ERP page available')
p.stop()
