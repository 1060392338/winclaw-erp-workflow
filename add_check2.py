#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
path = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\run_workflow.py"
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

old = '''    # 场景A：直接发布模式（跳过审核认领）'''
new = '''    # 场景A0：查看草稿箱（不发布）
    if args.check_draft:
        if not args.claim_to:
            print("  ?? 请用 --claim-to 指定店铺")
            return 1
        step("查看草稿箱商品")
        stdout, rc = run_script("run_publish.py", [args.claim_to, "--all"], timeout=120, retry=1)
        if stdout:
            import re
            lines = stdout.split("\\n")
            for line in lines:
                if '主货号' in line or '货源ID' in line or '标题' in line or '匹配' in line or '勾选' in line:
                    print(line)
            print("\\n  ??  以上是草稿箱商品（只查看，未发布）")
        return 0

    # 场景A：直接发布模式（跳过审核认领）'''

if old in c:
    c = c.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print('ADDED')
else:
    print('OLD NOT FOUND')
