#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')
path = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\run_workflow.py"
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# Add --check-draft after --products line
old = 'parser.add_argument("--products", default="", help="指定主货号发布（逗号分隔）")'
new = 'parser.add_argument("--check-draft", action="store_true", help="查看草稿箱商品列表（配合 --claim-to 使用）")\n    ' + old
if old in c:
    c = c.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(c)
    print('ADDED PARSER')
else:
    print('OLD NOT FOUND')
