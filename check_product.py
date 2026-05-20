#!/usr/bin/env python3
import sys; sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url:
            pg.locator('text=草稿箱').first.click()
            pg.wait_for_timeout(2000)
            tags = pg.locator('.t-tag--check')
            for i in range(tags.count()):
                if '順順' in tags.nth(i).text_content():
                    tags.nth(i).click()
                    break
            pg.wait_for_timeout(500)
            pg.locator('button:has-text("查询")').first.click()
            pg.wait_for_timeout(3000)
            rows = pg.evaluate('() => document.querySelectorAll("[class*=virtual-table-tr]").length')
            found = pg.locator('text=768896253679').count()
            print(f'rows={rows} found={"Y" if found>0 else "N"}', flush=True)
            body = pg.evaluate('document.body.innerText')
            if '768896253679' in body:
                print('IN_BODY=Y', flush=True)
            break
b.close(); p.stop()
