#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from infrastructure.config_loader import ConfigLoader
from playwright.sync_api import sync_playwright
_cfg = ConfigLoader().load()
port = _cfg.erp_cdp_ports[0]
p = sync_playwright().start()
b = p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
pg = b.new_page()
pg.goto(f'{_cfg.erp_url}/member/product/general/collect-box', wait_until='networkidle', timeout=20000)
pg.wait_for_timeout(5000)
# Try locator on multiple known pass IDs
pass_ids = ['626005526840','749523729233','856110744817','637676159743','681799856837','752344538588','713929588484','752344538588']
checked = 0
for eid in pass_ids:
    tr = pg.locator(f'tr:has-text("{eid}")')
    cnt = tr.count()
    if cnt > 0:
        cb = tr.first.locator('input[type="checkbox"]')
        if cb.count() > 0:
            cb.first.check(force=True, timeout=5000)
            checked += 1
            print(f'  OK {eid}')
        else:
            print(f'  NO_CB {eid}')
    else:
        print(f'  NO_TR {eid}')
print(f'Checked: {checked}/{len(pass_ids)}')
pg.close()
b.close()
p.stop()
