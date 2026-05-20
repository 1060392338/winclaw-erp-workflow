"""修补 run_workflow.py 的审查结果汇总部分"""
import re

path = r'C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\run_workflow.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = '''    if json_data:
        pass_count = json_data.get("pass_count", 0)
        reject_count = json_data.get("reject_count", 0)
        stores = json_data.get("stores", [])
        claimed_ids = json_data.get("claimed_product_ids", [])

        print(f"\\n  {'='*60}")
        print(f"  📊 合规审查结果汇总")
        print(f"  {'='*60}")
        print(f"  采集箱共: {pass_count + reject_count} 个商品")
        print(f"  ✅ 合规: {pass_count} 件")
        print(f"  ❌ 不合规: {reject_count} 件")
        print(f"  {'='*60}")
        print(f"  详细审查结果见上方实时输出")'''

new = '''    if json_data:
        pass_count = json_data.get("pass_count", 0)
        reject_count = json_data.get("reject_count", 0)
        stores = json_data.get("stores", [])
        claimed_ids = json_data.get("claimed_product_ids", [])

        # 从 stdout 中提取每条商品审查结果
        product_lines = []
        for _l in (stdout or "").split("\\n"):
            _m = re.match(r"^\\s+([✅❌])\\s+\\[([^\\]]+)\\]\\s+(.+)$", _l)
            if _m:
                product_lines.append({
                    "icon": _m.group(1),
                    "status": _m.group(2),
                    "title": _m.group(3).strip()
                })

        print(f"\\n  {'='*60}")
        print(f"  📊 合规审查结果汇总")
        print(f"  {'='*60}")
        print(f"  采集箱共: {pass_count + reject_count} 个商品")
        if product_lines:
            print(f"  {'='*60}")
            print(f"  ✅ 合规商品 ({pass_count} 件):")
            for _p in product_lines:
                if _p["icon"] == "✅":
                    print(f"    ✅ [{_p['status']}] {_p['title'][:55]}")
            if pass_count == 0:
                print("    (无)")
            print()
            print(f"  ❌ 不合规商品 ({reject_count} 件):")
            for _p in product_lines:
                if _p["icon"] == "❌":
                    print(f"    ❌ [{_p['status']}] {_p['title'][:55]}")
            if reject_count == 0:
                print("    (无)")
        else:
            print(f"  ✅ 合规: {pass_count} 件")
            print(f"  ❌ 不合规: {reject_count} 件")
        print(f"  {'='*60}")'''

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('REPLACED OK')
else:
    print('NOT FOUND - checking...')
    # 看看实际内容是什么
    if '📊 合规审查结果汇总' in content:
        idx = content.index('📊 合规审查结果汇总')
        print(content[idx-200:idx+300])
    else:
        print('Text not found at all')
