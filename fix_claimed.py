#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
path = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\run_compliance_claim.py"
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_start = '    # 认领后去发布页草稿箱，获取最新一批商品的主货号'
new_text = '''    # 获取本次认领商品的主货号 — 从已勾选的 checkbox 中提取，不是全量读草稿箱
    claimed_ids = []
    try:
        # 认领完成后弹窗关闭，在采集箱页面直接读 checkbox 已选行的主货号
        time.sleep(2)
        claimed_ids = page.evaluate("""() => {
            var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
            var ids = [];
            for (var i = 0; i < rows.length; i++) {
                var cb = rows[i].querySelector('input[type="checkbox"]');
                if (cb && (cb.checked || cb.getAttribute('checked') !== null)) {
                    var text = rows[i].textContent;
                    var m = text.match(/主货号[：:]\\s*(\\d+)/);
                    if (m) ids.push(m[1]);
                }
            }
            return ids;
        }""")
        if claimed_ids:
            print(f"  ??? 获取认领主货号: {len(claimed_ids)} 件")
        else:
            # 兜底：从 pass_ids 构造主货号
            claimed_ids = [str(pid) for pid in (pass_ids or [])]
            print(f"  ??? 从pass_ids获取主货号: {len(claimed_ids)} 件")
    except Exception as e:
        print(f"  ?? 获取主货号失败: {e}")
        claimed_ids = [str(pid) for pid in (pass_ids or [])]

    result["claimed"] = True
    result["claimed_product_ids"] = claimed_ids'''

idx = content.find(old_start)
if idx >= 0:
    # find the end of this block (next line starts with '    result["claimed"] = True')
    rest = content[idx:]
    old_end = rest.find('\n    result["claimed"] = True')
    if old_end >= 0:
        old_block = rest[:old_end + len('\n    result["claimed"] = True')]
        content = content.replace(old_block, new_text)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('REPLACED')
    else:
        print('END_NOT_FOUND')
else:
    print('BLOCK_NOT_FOUND')
