#!/usr/bin/env python3
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url:
            body = pg.evaluate('document.body.innerText')
            draft = re.findall(r'草稿箱[（(](\d+)[）)]', body)
            pending = re.findall(r'发布中[（(](\d+)[）)]', body)
            success = re.findall(r'发布成功[（(](\d+)[）)]', body)
            print(f'草稿箱: {draft[0] if draft else "?"}')
            print(f'发布中: {pending[0] if pending else "?"}')
            print(f'发布成功: {success[0] if success else "?"}')
            for pid in ['753372954474','752989483512','590658340073','758715653432']:
                if pid in body:
                    print(f'{pid}: 在页面中')
                else:
                    print(f'{pid}: 不在页面')
            break
p.stop()
