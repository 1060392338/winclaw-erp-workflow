#!/usr/bin/env python3
"""Fix indent issues in run_ext_collect.py and workflow_deepagent.py"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

# === Fix run_ext_collect.py ===
path1 = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\run_ext_collect.py"
with open(path1, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# The import block we inserted should be at the bottom of the file, 
# outside any function. The original had CDP_URL etc at module level.
# Remove our broken insertions and add proper module-level ones.
new_lines = []
skip_until_fix = False
for i, line in enumerate(lines):
    stripped = line.strip()
    
    # Skip the broken fix we inserted (python -c block)
    if stripped.startswith('# CDP_URL'):
        skip_until_fix = True
        continue
    if skip_until_fix:
        if stripped.startswith('CDP_URL') or stripped.startswith('from infrastructure') or stripped.startswith('_cfg') or stripped.startswith('_bm_ports'):
            skip_until_fix = False
            continue
        if skip_until_fix:
            continue
    
    # Fix target_domain indent
    if 'target_domain = domain_map.get' in stripped:
        indent = ' ' * 8
        new_lines.append(indent + 'target_domain = domain_map.get(platform, "1688")\n')
        continue
    
    new_lines.append(line)

# Now add the config import BEFORE CDP_URL definition
# Find where CDP_URL is defined (should be near top after imports)
cdp_idx = None
for i, line in enumerate(new_lines):
    if line.strip().startswith('CDP_URL ='):
        cdp_idx = i
        break

if cdp_idx is not None:
    # Add config loader import before CDP_URL
    insert = [
        '# 从 config.yaml 读取端口配置 — 修复硬编码\n',
        'from infrastructure.config_loader import ConfigLoader\n',
        '_ext_cfg = ConfigLoader().load()\n',
        '_ext_cdp_ports = _ext_cfg.erp_cdp_ports\n',
        '\n',
    ]
    for j, ins in enumerate(insert):
        new_lines.insert(cdp_idx + j, ins)
    # Update CDP_URL to use config
    for i, line in enumerate(new_lines):
        if line.strip().startswith('CDP_URL ='):
            new_lines[i] = 'CDP_URL = f"http://127.0.0.1:{_ext_cdp_ports[0]}"\n'
            break

with open(path1, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print("DONE: run_ext_collect.py")

# === Fix workflow_deepagent.py ===
path2 = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\workflow_deepagent.py"
with open(path2, 'r', encoding='utf-8') as f:
    content = f.read()

# The function indent is 8 spaces (inside async def check_hhh_plugin)
old = '''            from infrastructure.config_loader import ConfigLoader
            _wd_cfg = ConfigLoader().load()
            _wd_port = _wd_cfg.erp_cdp_ports[0]
            b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_wd_port}")'''

new = '''        from infrastructure.config_loader import ConfigLoader
        _wd_cfg = ConfigLoader().load()
        _wd_port = _wd_cfg.erp_cdp_ports[0]
        b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_wd_port}")'''

content = content.replace(old, new)

with open(path2, 'w', encoding='utf-8') as f:
    f.write(content)
print("DONE: workflow_deepagent.py")
