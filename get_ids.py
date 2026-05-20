#!/usr/bin/env python3
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'collect-box' in pg.url:
            text = pg.evaluate('document.body.innerText')
            ids = re.findall(r'[\u8d27\u6e90ID[：:]\\s*(\\d+)', text)
            print('IDs: ' + str(ids))
            break
b.close()
p.stop()
