#!/usr/bin/env python3
import sys, re
sys.stdout.reconfigure(encoding='utf-8')
from infrastructure.config_loader import ConfigLoader
from playwright.sync_api import sync_playwright
_cfg = ConfigLoader().load()
port = _cfg.erp_cdp_ports[0]
p = sync_playwright().start()
b = p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
page = b.new_page()
page.goto(f'{_cfg.erp_url}/member/product/shopee/publish', wait_until='networkidle', timeout=20000)
page.wait_for_timeout(3000)
# close dialogs
page.evaluate("() => { document.querySelectorAll('[class*=\"dialog\"]').forEach(d => { const c = d.querySelector('.t-dialog__close'); if(c) c.click(); }); }")
page.wait_for_timeout(1000)
# Get tab counts
body = page.evaluate('document.body.innerText')
print('TEXT:', body[:500])
draft = re.findall(r'草稿箱[（(](\d+)[）)]', body)
pending = re.findall(r'发布中[（(](\d+)[）)]', body)
success = re.findall(r'发布成功[（(](\d+)[）)]', body)
print(f'草稿箱: {draft[0] if draft else "?"}')
print(f'发布中: {pending[0] if pending else "?"}')
print(f'发布成功: {success[0] if success else "?"}')
page.close(); b.close(); p.stop()
