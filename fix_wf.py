#!/usr/bin/env python3
path = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\workflow_deepagent.py"
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()
old = 'b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")'
new = '''from infrastructure.config_loader import ConfigLoader
        _wd_cfg = ConfigLoader().load()
        _wd_port = _wd_cfg.erp_cdp_ports[0]
        b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_wd_port}")'''
c = c.replace(old, new)
with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
print("DONE")
