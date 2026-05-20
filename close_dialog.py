#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
from infrastructure.config_loader import ConfigLoader
from playwright.sync_api import sync_playwright
_cfg = ConfigLoader().load()
port = _cfg.erp_cdp_ports[0]
p = sync_playwright().start()
b = p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'collect-box' in pg.url or 'member' in pg.url:
            pg.evaluate("() => { document.querySelectorAll('[class*=\"dialog\"]').forEach(d => { const c = d.querySelector('.t-dialog__close'); if(c) c.click(); }); }")
            pg.wait_for_timeout(1000)
            print('Dialogs closed')
            b.close()
            p.stop()
            exit()
print('No ERP tab')
b.close()
p.stop()
