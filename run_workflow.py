#!/usr/bin/env python3
"""
一键全流程编排：采集→审核→删除→认领→发布
不依赖 deepagent LLM，纯脚本确定性执行。

┌─────────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐    ┌─────────┐
│  采集(预留)  │ → │ 审核+删除 │ → │  认领    │ → │  发布   │ → │  完成   │
│ PDD/1688/.. │   │ 图片优先 │   │ 用户确认 │   │ 主货号  │   │         │
└─────────────┘   └──────────┘    └──────────┘   └─────────┘   └─────────┘

用法:
    # 全流程：审核→删除→认领→发布
    python run_workflow.py --claim-to "店铺名"

    # 从采集开始全流程（采集模块预留接口）
    # python run_workflow.py --collect "PDD店铺名" -n 5 --claim-to "店铺名"

    # 只审核认领，不发布
    python run_workflow.py --claim-to "店铺名" --skip-publish

    # 直接发布到指定店铺（跳过审核认领）
    python run_workflow.py --claim-to "店铺名" --publish --products id1,id2
    python run_workflow.py --claim-to "店铺名" --publish --all

    # 查看草稿箱商品
    python run_workflow.py --claim-to "店铺名" --check-draft

    # 从状态文件恢复认领（弹窗已打开）
    python run_workflow.py --claim-to "店铺名" --resume
"""
import sys, json, subprocess, argparse, time
from pathlib import Path

PROJECT = Path(__file__).parent

def step(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")

def run_script(name, args, timeout=600, retry=1):
    """运行项目内脚本，实时输出，返回 stdout。失败时自动重试。"""
    for attempt in range(retry + 1):
        cmd = [sys.executable, name] + args
        print(f"  $ {' '.join(cmd)}", flush=True)
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   encoding='utf-8', errors='replace')
            
            # 实时读取 stdout，逐行打印
            stdout_lines = []
            for line in proc.stdout:
                print(line, end='', flush=True)
                stdout_lines.append(line)
            
            # 读取 stderr（过滤已知警告）
            stderr_out = proc.stderr.read()
            if stderr_out:
                err_lines = [l for l in stderr_out.split('\n')
                            if 'DeprecationWarning' not in l and 'SyntaxWarning' not in l]
                if err_lines:
                    filtered = [l for l in err_lines if l.strip()]
                    if filtered:
                        msg = '; '.join(filtered[-3:])
                        try:
                            print(f"  stderr: {msg}", flush=True)
                        except UnicodeEncodeError:
                            print(f"  stderr: {msg.encode('utf-8', errors='replace').decode('utf-8')}", flush=True)

            proc.wait(timeout=timeout)
            stdout = ''.join(stdout_lines)
            rc = proc.returncode

            if rc == 0:
                return stdout, 0

            if '--JSON--' in stdout:
                return stdout, rc

            if attempt < retry:
                print(f"  ⚠️ 退出码 {rc}，{attempt+1}/{retry} 重试...", flush=True)
                time.sleep(3)
            else:
                return stdout, rc

        except subprocess.TimeoutExpired:
            if attempt < retry:
                print(f"  ⚠️ 超时，{attempt+1}/{retry} 重试...", flush=True)
                time.sleep(3)
            else:
                print(f"  ❌ 超时 {timeout}s", flush=True)
                return "", -1
        except Exception as e:
            print(f"  ❌ 异常: {e}", flush=True)
            return "", -1

    return "", -1


ASSIGNMENT_RULES_FILE = Path(__file__).parent / "assignment_rules.json"


def parse_json_output(stdout):
    if "--JSON--" in stdout:
        json_str = stdout.split("--JSON--")[-1].strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    return None


def _load_assignment_rules() -> dict:
    if ASSIGNMENT_RULES_FILE.exists():
        try:
            return json.loads(ASSIGNMENT_RULES_FILE.read_text(encoding='utf-8'))
        except:
            pass
    return {"category_rules": [], "product_rules": []}


def _save_assignment_rules(rules: dict):
    ASSIGNMENT_RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding='utf-8')


def _apply_assignment_rules(pass_products, stores, store_category_map):
    rules = _load_assignment_rules()
    category_rules = {r["category"]: r["store"] for r in rules.get("category_rules", [])}
    product_rules = {r["product_id"]: r["store"] for r in rules.get("product_rules", [])}
    store_assignments = {}
    unassigned = []
    for _p in pass_products:
        pid = _p.get('id', '')
        cat = _p.get('category', '') or '未分类'
        if pid in product_rules:
            s = product_rules[pid]
            store_assignments.setdefault(s, []).append(_p)
            continue
        if cat in category_rules:
            s = category_rules[cat]
            store_assignments.setdefault(s, []).append(_p)
            continue
        assigned = False
        for s_name, cats in store_category_map.items():
            if cat in cats:
                store_assignments.setdefault(s_name, []).append(_p)
                assigned = True
                break
        if not assigned:
            unassigned.append(_p)
    return store_assignments, unassigned



def _claim_and_publish_for_store(PROJECT, run_script, store_name, product_ids, skip_publish=False, skip_claim=False):
    """认领并发布商品到指定店铺。

    Args:
        skip_claim: True 时跳过认领（第一阶段 --claim-to 已认领），直接发布
    """
    import time as _time
    if not product_ids:
        print("  \u26a0\ufe0f \u65e0\u5546\u54c1\uff0c\u8df3\u8fc7\u53d1\u5e03")
        return

    if not skip_claim:
        # \u9700\u8981\u8ba4\u9886\uff08\u591a\u5e97\u94fa\u5206\u914d\u573a\u666f\uff09\uff1a\u8c03 --direct-claim
        step(f"\u8ba4\u9886\u5230 \u2192 {store_name}")
        pid_str = ",".join(product_ids)
        claim_out, _ = run_script("run_compliance_claim.py", ["--claim-to", store_name, "--direct-claim", pid_str], timeout=300, retry=1)
        if claim_out and "--JSON--" in claim_out:
            try:
                claim_json = json.loads(claim_out.split("--JSON--")[-1].strip())
                claimed = claim_json.get("claimed_product_ids", [])
                if claimed:
                    product_ids = [str(c) for c in claimed]
                    print(f"  \u2705 \u5b9e\u9645\u8ba4\u9886\u6210\u529f {len(product_ids)} \u4ef6", flush=True)
            except:
                pass
        if not product_ids:
            print("  \u26a0\ufe0f \u65e0\u5b9e\u9645\u8ba4\u9886\u6210\u529f\u7684\u5546\u54c1\uff0c\u8df3\u8fc7\u53d1\u5e03")
            return
    else:
        print(f"  \u2192 \u7b2c\u4e00\u9636\u6bb5\u5df2\u8ba4\u9886\uff0c\u76f4\u63a5\u53d1\u5e03 {len(product_ids)} \u4ef6")

    if skip_publish:
        print(f"  \u2705 \u5e97\u94fa\u300c{store_name}\u300d\u5904\u7406\u5b8c\u6210\uff0c\u8df3\u8fc7\u53d1\u5e03")
        return

    step(f"\u53d1\u5e03\u524d\u6821\u9a8c \u2192 {store_name}")
    max_wait = 300
    found_all = False
    for attempt in range(max_wait // 10):
        _time.sleep(10)
        found = []
        not_found = []
        for pid in product_ids:
            wait_out, _ = run_script("run_publish.py", [store_name, "--check-product", pid], timeout=30, retry=0)
            if pid in wait_out:
                found.append(pid)
            else:
                not_found.append(pid)
        if not not_found:
            found_all = True
            break
        print(f"  \u23f3 \u7b49\u5f85\u4e2d ({len(found)}/{len(product_ids)} \u5df2\u5230)...", flush=True)
    if not found_all:
        print(f"  \u26a0\ufe0f \u7b49\u5f85\u8d85\u65f6\uff0c\u90e8\u5206\u5546\u54c1\u53ef\u80fd\u672a\u540c\u6b65: {not_found}")
        product_ids = found
        if not product_ids:
            print("  \u274c \u6ca1\u6709\u53ef\u53d1\u5e03\u7684\u5546\u54c1")
            return
    step(f"\u53d1\u5e03\u5230 {store_name}")
    pid_str = ",".join(product_ids)
    run_script("run_publish.py", [store_name, "--products", pid_str], timeout=300, retry=1)
    print(f"  \u2705 \u5e97\u94fa\u300c{store_name}\u300d\u53d1\u5e03\u5b8c\u6210 ({len(product_ids)}\u4ef6)")


def _cleanup_and_finish(PROJECT, run_script, overall_results):
    step("  ↩️ 清理采集箱残留...")
    run_script("run_compliance_claim.py", ["--delete-rejected"], timeout=120, retry=1)
    print(f"\n{'='*60}")
    print(f"  🎉 全流程完成!")
    for store, ids in overall_results:
        print(f"    店铺「{store}」: {len(ids)}件")
    print(f"  {'='*60}")


def main():
    parser = argparse.ArgumentParser(description="跨境ERP 采集→审核→删除→认领→发布 一键编排")
    parser.add_argument("--claim-to", default="", help="认领/发布到目标店铺")
    parser.add_argument("--resume", action="store_true", help="从状态文件恢复认领（弹窗已打开）")
    parser.add_argument("--skip-publish", action="store_true", help="只做审核认领，跳过发布")
    parser.add_argument("--publish", action="store_true", help="直接发布模式（跳过审核认领）")
    parser.add_argument("--all", action="store_true", help="发布全部草稿（配合 --publish 使用）")
    parser.add_argument("--check-draft", action="store_true", help="查看草稿箱商品列表（配合 --claim-to 使用）")
    parser.add_argument("--products", default="", help="指定主货号发布（逗号分隔）")
    # ════════════════ 采集模块参数（预留）════════════════
    parser.add_argument("--add-rule", default="", help="添加持久化分配规则。格式：category:类目名->店名 或 product:商品ID->店名")
    parser.add_argument("--collect", action="store_true", help="【预留】先采集再审核发布")
    parser.add_argument("shops", nargs="*", default=[], help="【预留】PDD店铺名")
    parser.add_argument("-n", "--topn", type=int, default=2, help="【预留】每店采集N件")
    parser.add_argument("-k", "--keyword", default="", help="【预留】店内搜索关键词")
    # ════════════════════════════════════════════════════════
    args = parser.parse_args()

    # ============================================================
    # 场景：添加持久化规则（不跑流程）
    if args.add_rule:
        rules = _load_assignment_rules()
        rule_str = args.add_rule.strip()
        if rule_str.startswith("category:"):
            parts = rule_str[9:].split("->", 1)
            if len(parts) == 2:
                cat, store = parts[0].strip(), parts[1].strip()
                rules["category_rules"] = [r for r in rules.get("category_rules", []) if r["category"] != cat]
                rules["category_rules"].append({"category": cat, "store": store})
                _save_assignment_rules(rules)
                print(f"  \u2714 \u6dfb\u52a0\u7c7b\u76ee\u89c4\u5219: [{cat}] -> {store}")
                return 0
        elif rule_str.startswith("product:"):
            parts = rule_str[8:].split("->", 1)
            if len(parts) == 2:
                pid, store = parts[0].strip(), parts[1].strip()
                rules["product_rules"] = [r for r in rules.get("product_rules", []) if r["product_id"] != pid]
                rules["product_rules"].append({"product_id": pid, "store": store})
                _save_assignment_rules(rules)
                print(f"  \u2714 \u6dfb\u52a0\u5546\u54c1\u89c4\u5219: \u4e3b\u8d27\u53f7({pid}) -> {store}")
                return 0
        print(f"  \u2716 \u89c4\u5219\u683c\u5f0f\u9519\u8bef\u3002\u6b63\u786e\u683c\u5f0f\uff1acategory:\u7c7b\u76ee\u540d->\u5e97\u540d \u6216 product:\u5546\u54c1ID->\u5e97\u540d")
        return 1

    # ============================================================
    # 场景A0：查看草稿箱（不发布）
    if args.check_draft:
        if not args.claim_to:
            print("  ?? 请用 --claim-to 指定店铺")
            return 1
        step("查看草稿箱商品")
        stdout, rc = run_script("run_publish.py", [args.claim_to, "--all"], timeout=120, retry=1)
        if stdout:
            import re
            lines = stdout.split("\n")
            for line in lines:
                if '主货号' in line or '货源ID' in line or '标题' in line or '匹配' in line or '勾选' in line:
                    print(line)
            print("\n  ??  以上是草稿箱商品（只查看，未发布）")
        return 0

    # 场景A：直接发布模式（跳过审核认领）
    # ============================================================
    if args.publish:
        step("直接发布模式 → 跳过审核认领")

        if not args.claim_to:
            print("  ❌ 请用 --claim-to 指定发布店铺")
            return 1

        if args.products:
            run_script("run_publish.py", [args.claim_to, "--products", args.products], timeout=300, retry=1)
        elif args.all:
            run_script("run_publish.py", [args.claim_to, "--all"], timeout=300, retry=1)
        else:
            print("  ⚠️ 请指定要发布的商品:")
            print(f"     --products id1,id2  指定主货号发布")
            print(f"     --all               发布全部草稿")
            return 1

        print(f"\n{'='*60}")
        print(f"  ✅ 发布完成!")
        print(f"{'='*60}")
        return 0

    # ════════════════ 采集阶段（预留接口）════════════════
    if args.collect:
        step("【预留】采集阶段 → 暂未实现")
        print("  采集参数: shops=%s, topn=%d, keyword=%s" % (args.shops, args.topn, args.keyword))
        print("  需接入 run_store_collect_flow.py / run_ext_collect.py")
        # 将来实现:
        # for shop in args.shops:
        #     run_script("run_store_collect_flow.py", [shop, "-n", str(args.topn), "-k", args.keyword])
    # ════════════════════════════════════════════════════════════

    # ============================================================
    # 场景B：完整流程 审核→删除→认领→发布
    # ============================================================
    step("阶段1/3: 合规审查 → 删除不合规商品")

    if args.resume:
        stdout, rc = run_script("run_compliance_claim.py", [
            "--claim-to", args.claim_to, "--resume"
        ], timeout=600, retry=1)
    elif args.claim_to:
        stdout, rc = run_script("run_compliance_claim.py", [
            "--claim-to", args.claim_to
        ], timeout=600, retry=2)
    else:
        stdout, rc = run_script("run_compliance_claim.py", [
            "--list-stores"
        ], timeout=600, retry=2)

    json_data = parse_json_output(stdout)
    if json_data:
        pass_count = json_data.get("pass_count", 0)
        reject_count = json_data.get("reject_count", 0)
        stores = json_data.get("stores", [])
        claimed_ids = json_data.get("claimed_product_ids", [])

        # 从 stdout 中提取每条商品审查结果
        import re as _re
        _product_lines = []
        for _l in (stdout or "").split("\n"):
            _m = _re.match(r"^\s+([✅❌])\s+\[([^\]]+)\]\s+(.+)$", _l)
            if _m:
                _product_lines.append({"icon": _m.group(1), "status": _m.group(2), "title": _m.group(3).strip()})

        print(f"\n  {'='*60}")
        print(f"  📊 合规审查结果汇总")
        print(f"  {'='*60}")
        print(f"  采集箱共: {pass_count + reject_count} 个商品")
        if _product_lines:
            print(f"  {'='*60}")
            print(f"  ✅ 合规商品 ({pass_count} 件):")
            for _p in _product_lines:
                if _p["icon"] == "✅":
                    print(f"    ✅ [{_p['status']}] {_p['title'][:55]}")
            if pass_count == 0:
                print("    (无)")
            print()
            print(f"  ❌ 不合规商品 ({reject_count} 件):")
            for _p in _product_lines:
                if _p["icon"] == "❌":
                    print(f"    ❌ [{_p['status']}] {_p['title'][:55]}")
            if reject_count == 0:
                print("    (无)")
        else:
            print(f"  ✅ 合规: {pass_count} 件")
            print(f"  ❌ 不合规: {reject_count} 件")
        print(f"  {'='*60}")

        # 如果还有被拒商品但删除可能没成功，再调一次 --delete-rejected 确保删除
        if reject_count > 0:
            step("  🔄 确保删除不合规商品...")
            del_stdout, del_rc = run_script("run_compliance_claim.py", [
                "--delete-rejected"
            ], timeout=120, retry=2)

        if stores:
            print(f"    可用店铺: {', '.join(stores)}")

        # 无通过商品 → 结束
        if pass_count == 0:
            print("\n  ℹ️  无合规商品可认领，流程结束")
            return 0

        pass_products = json_data.get("pass_products", [])

        step("阶段2/3: 应用分配规则")

        # 读取店铺类目映射表
        store_category_map = {}
        map_file = PROJECT / "store_category_map.json"
        if map_file.exists():
            try:
                store_category_map = json.loads(map_file.read_text(encoding='utf-8'))
            except Exception as e:
                print(f"   \u8bfb\u53d6\u5e97\u94fa\u7c7b\u76ee\u6620\u5c04\u8868\u5931\u8d25: {e}", flush=True)

        store_assignments, unassigned = _apply_assignment_rules(pass_products, stores, store_category_map)

        if store_assignments:
            print("\n   \u5206\u914d\u7ed3\u679c:")
            for s_name, prods in store_assignments.items():
                print(f"    [{s_name}]\u2190 {len(prods)}\u4ef6")
                for _p in prods:
                    cat = _p.get('category', '') or '\u672a\u5206\u7c7b'
                    print(f"      [{cat}] \u4e3b\u8d27\u53f7({_p.get('id','?')})")
            for s_name, prods in store_assignments.items():
                pids = [p.get('id', '') for p in prods if p.get('id')]
                if pids:
                    print(f"\n  -> \u8ba4\u9886\u53d1\u5e03\u5230[{s_name}]({len(pids)}\u4ef6)...")
                    _claim_and_publish_for_store(PROJECT, run_script, s_name, pids, args.skip_publish, skip_claim=bool(args.claim_to))

        if unassigned:
            print("\n   \u4ee5\u4e0b\u5546\u54c1\u65e0\u5339\u914d\u7684\u5e97\u94fa\u7c7b\u76ee\uff0c\u8bf7\u624b\u52a8\u5206\u914d\uff1a")
            for _i, _p in enumerate(unassigned, 1):
                cat = _p.get('category', '') or '\u672a\u5206\u7c7b'
                print(f"    {_i}. [{cat}] \u4e3b\u8d27\u53f7({_p.get('id','?')}) {_p.get('title','?')[:50]}")
            print("\n   \u53ef\u7528\u5e97\u94fa:")
            for i, s in enumerate(stores):
                print(f"    {i+1}. {s}")
            print("\n  \u8bf7\u544a\u8bc9\u6211\u8981\u600e\u4e48\u5206\u914d\uff08\u683c\u5f0f\u793a\u4f8b\uff1a\u5168\u90e8\u5230\u9806\u9806\u306e\u5c0f\u5c4b\u7ae5\u88dd \u6216 1\u5230\u9806\u9806\u306e\u5c0f\u5c4b\uff0c2\u5230\u5409\u8c61\u661f\u9023\u574a \u6216 \u670d\u88c5\u7c7b\u7684\u5230A\u5e97\uff0c3C\u7c7b\u7684\u5230B\u5e97\uff09")
            return 0

        if not store_assignments and not unassigned:
            pass
    else:
        print("   \u5ba1\u6838\u9636\u6bb5\u5931\u8d25\uff08\u65e0\u7ed3\u6784\u5316\u8f93\u51fa\uff09")
        return 1

    # 清理采集箱残留
    step("  \U0001f504 \u6e05\u7406\u91c7\u96c6\u7bb1\u6b8b\u7559...")
    run_script("run_compliance_claim.py", ["--delete-rejected"], timeout=120, retry=1)

    print(f"\n{'='*60}")
    print(f"  \U0001f389 \u5168\u6d41\u7a0b\u5b8c\u6210!")
    print(f"{'='*60}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
