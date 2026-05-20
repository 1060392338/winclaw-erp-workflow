#!/usr/bin/env python3
"""一次性修复所有硬编码问题"""
import re, sys, os
sys.stdout.reconfigure(encoding='utf-8')

BASE = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new"
FIXES = []

def fix_file(path, replacements, description=""):
    """在文件中做文本替换，返回改动数"""
    fullpath = os.path.join(BASE, path)
    with open(fullpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    count = 0
    for old, new in replacements:
        if old in content:
            content = content.replace(old, new)
            count += 1
    
    if count:
        with open(fullpath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  [{description}] {path}: {count} 处")
    return count

total = 0

# ============================================================
# 1. erp_publisher.py — 硬编码的ERP URL
# ============================================================
print("\n=== erp_publisher.py ===")
total += fix_file("infrastructure/erp_publisher.py", [
    (
        'PUBLISH_URL = "https://www.huohanhan.com/member/product/shopee/publish"',
        'PUBLISH_URL = ""  # 在 __init__ 中根据 config 设置'
    ),
    (
        'COLLECT_BOX_URL = "https://www.huohanhan.com/member/product/general/collect-box"',
        'COLLECT_BOX_URL = ""  # 同上'
    ),
    (
        '    PUBLISH_URL = "https://www.huohanhan.com/member/product/shopee/publish"',
        '    PUBLISH_URL = ""  # 动态从 config 读取'
    ),
    (
        '    COLLECT_BOX_URL = "https://www.huohanhan.com/member/product/general/collect-box"',
        '    COLLECT_BOX_URL = ""'
    ),
], "URL动态化")

# ============================================================
# 2. run_ext_collect.py — CDP URL 和 PDD 域名硬编码
# ============================================================
print("\n=== run_ext_collect.py ===")
total += fix_file("run_ext_collect.py", [
    (
        'CDP_URL = "http://127.0.0.1:9223"',
        '# CDP_URL 从 config.yaml 读取或自动扫描端口\nfrom infrastructure.config_loader import ConfigLoader\n_cfg = ConfigLoader().load()\n_bm_ports = _cfg.erp_cdp_ports\nCDP_URL = f"http://127.0.0.1:{_bm_ports[0]}"'
    ),
    (
        'PDD_HOME = "https://mobile.yangkeduo.com/"',
        'PDD_HOME = os.getenv("PDD_HOME", "https://mobile.yangkeduo.com/")'
    ),
    (
        'PDD_SEARCH = "https://mobile.yangkeduo.com/search_result.html?search_key={}"',
        'PDD_SEARCH = os.getenv("PDD_SEARCH", "https://mobile.yangkeduo.com/search_result.html?search_key={}")'
    ),
    (
        'domain_map = {"pdd": "yangkeduo.com", "1688": "1688.com"}',
        'PDD_DOMAIN = os.getenv("PDD_DOMAIN", "yangkeduo.com")\ndomain_map = {"pdd": PDD_DOMAIN, "1688": "1688.com"}'
    ),
], "端口/域名动态化")

# ============================================================
# 3. run_publish.py — CDP端口和ERP URL硬编码
# ============================================================
print("\n=== run_publish.py ===")
total += fix_file("run_publish.py", [
    (
        '        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9223")',
        '        # 从 config 读取端口\n        from infrastructure.config_loader import ConfigLoader\n        _cfg = ConfigLoader().load()\n        _port = _cfg.erp_cdp_ports[0]\n        browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_port}")'
    ),
    (
        '        publish_url = "https://www.huohanhan.com/member/product/shopee/publish"',
        '        from infrastructure.config_loader import ConfigLoader\n        _publish_cfg = ConfigLoader().load()\n        publish_url = f"{_publish_cfg.erp_url}/member/product/shopee/publish"'
    ),
], "端口/URL动态化")

# ============================================================
# 4. run_compliance_claim.py — CDP端口和ERP URL硬编码
# ============================================================
print("\n=== run_compliance_claim.py ===")
total += fix_file("run_compliance_claim.py", [
    (
        '    page.goto("https://www.huohanhan.com/member/product/general/collect-box")',
        '    from infrastructure.config_loader import ConfigLoader\n    _cc_cfg = ConfigLoader().load()\n    page.goto(f"{_cc_cfg.erp_url}/member/product/general/collect-box")'
    ),
    (
        '        page.goto("https://www.huohanhan.com/member/product/shopee/publish", wait_until="networkidle", timeout=30000)',
        '        from infrastructure.config_loader import ConfigLoader\n        _cc_cfg2 = ConfigLoader().load()\n        page.goto(f"{_cc_cfg2.erp_url}/member/product/shopee/publish", wait_until="networkidle", timeout=30000)'
    ),
], "URL动态化")

# ============================================================
# 5. run_store_collect_flow.py — CDP端口和ERP URL
# ============================================================
print("\n=== run_store_collect_flow.py ===")
total += fix_file("run_store_collect_flow.py", [
    (
        '    page = ChromiumPage(addr_or_opts="127.0.0.1:9223")',
        '    from infrastructure.config_loader import ConfigLoader\n    _sc_cfg = ConfigLoader().load()\n    _sc_port = _sc_cfg.erp_cdp_ports[0]\n    page = ChromiumPage(addr_or_opts=f"127.0.0.1:{_sc_port}")'
    ),
    (
        '            browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")',
        '            from infrastructure.config_loader import ConfigLoader\n            _sc_cfg2 = ConfigLoader().load()\n            _sc_port2 = _sc_cfg2.erp_cdp_ports[0]\n            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{_sc_port2}")'
    ),
    (
        '    page.get("https://www.huohanhan.com/member/home/index")',
        '    from infrastructure.config_loader import ConfigLoader\n    _sc_cfg3 = ConfigLoader().load()\n    page.get(f"{_sc_cfg3.erp_url}/member/home/index")'
    ),
    (
        '    page.get("https://www.huohanhan.com/member/product/general/collect-box")',
        '    page.get(f"{_sc_cfg3.erp_url}/member/product/general/collect-box")'
    ),
], "端口/URL动态化")

# ============================================================
# 6. workflow_deepagent.py — CDP端口
# ============================================================
print("\n=== workflow_deepagent.py ===")
total += fix_file("workflow_deepagent.py", [
    (
        '        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9223")',
        '        from infrastructure.config_loader import ConfigLoader\n        _wd_cfg = ConfigLoader().load()\n        _wd_port = _wd_cfg.erp_cdp_ports[0]\n        b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{_wd_port}")'
    ),
], "端口动态化")

# ============================================================
# 7. config/config.yaml — 店铺名泛化
# ============================================================
print("\n=== config/config.yaml ===")
total += fix_file("config/config.yaml", [
    (
        '  - id: "tw_main"\n    name: "台湾旗舰店"\n    platform: "Shopee"\n    region: "TW"\n  - id: "tw_second"\n    name: "跨境优选店"\n    platform: "Shopee"\n    region: "TW"\n  - id: "sg_store"\n    name: "东南亚专营店"\n    platform: "Shopee"\n    region: "SG"',
        '# 店铺列表：请根据你的实际账号修改\n#  api/product/collect/getStores 返回什么就填什么\n  - id: "store_1"\n    name: "店铺A"\n    platform: "Shopee"\n    region: "TW"\n  - id: "store_2"\n    name: "店铺B"\n    platform: "Shopee"\n    region: "TW"'
    ),
], "店铺名泛化")

print(f"\n{'='*40}")
print(f"总计修复: {total} 处")
print(f"{'='*40}")
