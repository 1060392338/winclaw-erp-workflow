#!/usr/bin/env python3
"""Fix run_workflow.py:
1. _claim_and_publish_for_store: skip direct-claim, go straight to publish
2. run_script: fix GBK stderr encoding error
"""

path = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\run_workflow.py"

with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Fix run_script stderr printing (GBK safe)
old_stderr = """            if err_lines:
                    filtered = [l for l in err_lines if l.strip()]
                    if filtered:
                        print(f"  stderr: {'; '.join(filtered[-3:])}", flush=True)"""

new_stderr = """            if err_lines:
                    filtered = [l for l in err_lines if l.strip()]
                    if filtered:
                        msg = '; '.join(filtered[-3:])
                        try:
                            print(f"  stderr: {msg}", flush=True)
                        except UnicodeEncodeError:
                            print(f"  stderr: {msg.encode('utf-8', errors='replace').decode('utf-8')}", flush=True)"""

if old_stderr in text:
    text = text.replace(old_stderr, new_stderr)
    print("1. Fixed GBK stderr printing")
else:
    print("1. SKIP: stderr block not found")
    # print repr of the area around 'if filtered:'
    idx = text.find('if filtered:')
    if idx != -1:
        print(f"  Found at {idx}: {repr(text[idx:idx+100])}")

# 2. Replace _claim_and_publish_for_store to skip direct-claim
old_func = """def _claim_and_publish_for_store(PROJECT, run_script, store_name, product_ids, skip_publish=False):
    import time as _time
    step(f"认领到\\u2192 {store_name}")
    pid_str = ",".join(product_ids)
    claim_out, _ = run_script("run_compliance_claim.py", ["--claim-to", store_name, "--direct-claim", pid_str], timeout=300, retry=1)
    if claim_out and "--JSON--" in claim_out:
        try:
            claim_json = json.loads(claim_out.split("--JSON--")[-1].strip())
            claimed = claim_json.get("claimed_product_ids", [])
            if claimed:
                product_ids = [str(c) for c in claimed]
                print(f"  \\u2705 \\u5b9e\\u9645\\u8ba4\\u9886\\u6210\\u529f {len(product_ids)} \\u4ef6", flush=True)
        except:
            pass
    if not product_ids:
        print("  \\u26a0\\ufe0f \\u65e0\\u5b9e\\u9645\\u8ba4\\u9886\\u6210\\u529f\\u7684\\u5546\\u54c1\\uff0c\\u8df3\\u8fc7\\u53d1\\u5e03")
        return
    if skip_publish:
        print(f"  \\u2705 \\u8ba4\\u9886\\u5230\\u300c{store_name}\\u300d\\u5b8c\\u6210\\uff0c\\u8df3\\u8fc7\\u53d1\\u5e03")
        return
    step(f"\\u53d1\\u5e03\\u524d\\u6821\\u9a8c \\u2192 {store_name}")"""

new_func = """def _claim_and_publish_for_store(PROJECT, run_script, store_name, product_ids, skip_publish=False):
    \"\"\"\\u53d1\\u5e03\\u5546\\u54c1\\u5230\\u6307\\u5b9a\\u5e97\\u94fa\\u3002
    \\u6ce8\\u610f\\uff1a\\u8ba4\\u9886\\u5df2\\u5728\\u7b2c\\u4e00\\u9636\\u6bb5\\uff08--claim-to\\uff09\\u5b8c\\u6210\\uff0c\\u6b64\\u51fd\\u6570\\u53ea\\u8d1f\\u8d23\\u53d1\\u5e03\\u3002
    \\u591a\\u5e97\\u94fa\\u5206\\u914d\\u573a\\u666f\\u4e0b\\uff0c\\u6b64\\u5904\\u5e94\\u901a\\u8fc7 --direct-claim \\u8ba4\\u9886\\u5230\\u4e0d\\u540c\\u5e97\\u94fa\\u3002
    \"\"\"
    import time as _time
    if not product_ids:
        print("  \\u26a0\\ufe0f \\u65e0\\u5546\\u54c1\\uff0c\\u8df3\\u8fc7\\u53d1\\u5e03")
        return
    if skip_publish:
        print(f"  \\u2705 \\u5df2\\u8ba4\\u9886\\u5230\\u300c{store_name}\\u300d\\uff0c\\u8df3\\u8fc7\\u53d1\\u5e03")
        return
    step(f"\\u53d1\\u5e03\\u524d\\u6821\\u9a8c \\u2192 {store_name}")"""

if old_func in text:
    text = text.replace(old_func, new_func)
    print("2. Replaced _claim_and_publish_for_store")
else:
    print("2. SKIP: function not found")
    # Try to find it with different escaping
    idx = text.find('def _claim_and_publish_for_store')
    if idx != -1:
        print(f"  Found at {idx}")
        print(f"  Next 200 chars:")
        for c in text[idx:idx+200]:
            print(f"    U+{ord(c):04X} = {c}")
    else:
        print("  NOT FOUND at all")

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Done!")
