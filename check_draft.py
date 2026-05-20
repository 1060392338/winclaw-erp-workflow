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
# click draft tab
try:
    page.locator('text=草稿箱').first.click()
    page.wait_for_timeout(2000)
except Exception as e:
    print(f'Draft tab click: {e}')

body = page.evaluate('document.body.innerText')
draft = re.findall(r'草稿箱[（(](\d+)[）)]', body)
success = re.findall(r'发布成功[（(](\d+)[）)]', body)
print(f'草稿箱: {draft[0] if draft else "0"} 件')
print(f'发布成功: {success[0] if success else "0"} 件')

# search for 断布机
try:
    page.locator('input').first.fill('断布机')
    page.wait_for_timeout(500)
    page.locator('button:has-text("查询")').first.click()
    page.wait_for_timeout(3000)
except:
    pass
cnt = page.locator('text=626005526840').count()
print(f'断布机626005526840: {"找到" if cnt > 0 else "未找到"}')
page.close(); b.close(); p.stop()
