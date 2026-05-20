#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'collect-box' in pg.url or 'member' in pg.url:
            # 切未认领
            pg.locator('text=未认领').first.click()
            pg.wait_for_timeout(3000)
            ids = pg.evaluate("""() => {
                var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
                return Array.from(rows).map(function(r){var m=r.textContent.match(/货源ID[：:]\\s*(\\d+)/);return m?m[1]:null;}).filter(Boolean);
            }""")
            print(f'未认领: {len(ids)} 个', flush=True)
            if ids:
                print(f'IDs: {ids}', flush=True)
            
            # 看看全部tab
            try:
                pg.locator('text=全部').first.click()
                pg.wait_for_timeout(2000)
                all_ids = pg.evaluate("""() => {
                    var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
                    return Array.from(rows).map(function(r){var m=r.textContent.match(/货源ID[：:]\\s*(\\d+)/);return m?m[1]:null;}).filter(Boolean);
                }""")
                print(f'全部: {len(all_ids)} 个', flush=True)
            except:
                pass
            break
p.stop()
