#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Fix run_ext_collect.py indent
path = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\run_ext_collect.py"
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    stripped = line.lstrip()
    # Fix the domain_map import block indent
    if stripped.startswith('# CDP_URL 从 config.yaml'):
        new_lines.append('        # CDP_URL 从 config.yaml 读取或自动扫描端口\n')
    elif stripped.startswith('from infrastructure.config_loader'):
        new_lines.append('        from infrastructure.config_loader import ConfigLoader\n')
    elif stripped.startswith('_cfg = ConfigLoader'):
        new_lines.append('        _cfg = ConfigLoader().load()\n')
    elif stripped.startswith('_bm_ports = _cfg'):
        new_lines.append('        _bm_ports = _cfg.erp_cdp_ports\n')
    elif stripped.startswith('CDP_URL = f"http'):
        new_lines.append('        CDP_URL = f"http://127.0.0.1:{_bm_ports[0]}"\n')
    elif 'target_domain = domain_map.get(' in stripped:
        new_lines.append('        target_domain = domain_map.get(platform, "1688")\n')
    elif 'PDD_DOMAIN = os.getenv' in stripped:
        new_lines.append('PDD_DOMAIN = os.getenv("PDD_DOMAIN", "yangkeduo.com")\n')
    elif 'domain_map = {"pdd": PDD_DOMAIN' in stripped:
        new_lines.append('domain_map = {"pdd": PDD_DOMAIN, "1688": "1688.com"}\n')
    else:
        new_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("DONE: run_ext_collect.py")

# Fix workflow_deepagent.py indent
path2 = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\workflow_deepagent.py"
with open(path2, 'r', encoding='utf-8') as f:
    content = f.read()

# The import is in the middle of an async function (12 spaces)
old_block = '''from infrastructure.config_loader import ConfigLoader
        _wd_cfg = ConfigLoader().load()
        _wd_port = _wd_cfg.erp_cdp_ports[0]
        b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_wd_port}")'''
new_block = '''            from infrastructure.config_loader import ConfigLoader
            _wd_cfg = ConfigLoader().load()
            _wd_port = _wd_cfg.erp_cdp_ports[0]
            b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_wd_port}")'''
content = content.replace(old_block, new_block)

with open(path2, 'w', encoding='utf-8') as f:
    f.write(content)
print("DONE: workflow_deepagent.py")
