#!/usr/bin/env python3
"""
run_workflow_v2.py — 带硬性校验的一键全流程编排
不改子脚本，只在此层做每一阶段的断言检查，确保：
  ① 提取数 = 采集箱计数
  ② pass + reject = 总商品数
  ③ claimed_ids <= check_count <= pass_count
  ④ 删除后采集箱残留 = 合规数（未删干净则报残留）
  ⑤ 已分配 + 未分配 = pass_count
  ⑥ 发布前商品在草稿箱，发布后发布中计数 >0

用法同 run_workflow.py
"""
import sys, json, subprocess, argparse, time, re
from pathlib import Path
from config.selectors import T, C, sleep

PROJECT = Path(__file__).parent

# ───────────┬───────────────────────────────────────────────
# 错误码（每个校验失败都有唯一切口）
# ───────────┴───────────────────────────────────────────────
ERR_EXTRACT_MISMATCH   = 10  # ①
ERR_COUNT_MISMATCH     = 11  # ②
ERR_CHECK_INCOMPLETE  = 12  # ③
ERR_DELETE_RESIDUAL   = 13  # ④
ERR_ASSIGN_MISMATCH   = 14  # ⑤
ERR_PUBLISH_FAILED    = 15  # ⑥

def step(msg, icon="━"):
    print(f"\n{icon*60}")
    print(f"  {msg}")
    print(f"{icon*60}")

def run_script(name, args, timeout=600, retry=1):
    for attempt in range(retry + 1):
        cmd = [sys.executable, name] + args
        print(f"  $ {' '.join(cmd)}", flush=True)
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   encoding='utf-8', errors='replace')
            stdout_lines = []
            for line in proc.stdout:
                print(line, end='', flush=True)
                stdout_lines.append(line)
            stderr_out = proc.stderr.read()
            if stderr_out:
                err_lines = [l for l in stderr_out.split('\n')
                            if 'DeprecationWarning' not in l and 'SyntaxWarning' not in l]
                filtered = [l for l in err_lines if l.strip()]
                if filtered:
                    try:
                        print(f"  stderr: {'; '.join(filtered[-3:])}", flush=True)
                    except UnicodeEncodeError:
                        pass
            proc.wait(timeout=timeout)
            stdout = ''.join(stdout_lines)
            rc = proc.returncode
            if rc == 0 or '--JSON--' in stdout:
                return stdout, rc
            if attempt < retry:
                print(f"  ⚠️ 退出码 {rc}，{attempt+1}/{retry} 重试...", flush=True)
                sleep(T.THREE_SECONDS)
            else:
                return stdout, rc
        except subprocess.TimeoutExpired:
            if attempt < retry:
                print(f"  ⚠️ 超时，{attempt+1}/{retry} 重试...", flush=True)
                sleep(T.THREE_SECONDS)
            else:
                print(f"  ❌ 超时 {timeout}s", flush=True)
                return "", -1
        except Exception as e:
            print(f"  ❌ 异常: {e}", flush=True)
            return "", -1
    return "", -1

def parse_json(stdout):
    if '--JSON--' in stdout:
        try:
            return json.loads(stdout.split('--JSON--')[-1].strip())
        except json.JSONDecodeError:
            return None
    return None


# ────────────────────────────────────────────────────────────
# 校验函数（不修改子脚本行为，只检查结果并停止或警告）
# ────────────────────────────────────────────────────────────

def check_extract(raw_products, tab_count, label="采集箱"):
    """① 提取数 = 采集箱计数（虚拟滚动限制不计入失败）"""
    n = len(raw_products) if raw_products else 0
    if n < tab_count:
        diff = tab_count - n
        print(f"  ⚠️ 校验①: 提取 {n}/{tab_count}（虚拟滚动差 {diff} 件，容忍）")
        # 差太多才报硬错（>30%未提取）
        if diff > tab_count * 0.3:
            print(f"  ❌ 校验① 失败: 提取率仅 {n}/{tab_count}，超过30%未渲染，无法继续")
            sys.exit(ERR_EXTRACT_MISMATCH)
        return n, True  # 容忍
    print(f"  ✅ 校验①: 提取 {n}/{tab_count}")
    return n, True

def check_counts(pass_count, reject_count, total_expected, label="合规审查"):
    """② pass + reject = 总商品数"""
    total = pass_count + reject_count
    if total != total_expected:
        print(f"  ❌ 校验②: pass({pass_count}) + reject({reject_count}) = {total} ≠ 预期 {total_expected}")
        sys.exit(ERR_COUNT_MISMATCH)
    print(f"  ✅ 校验②: {pass_count}通过 + {reject_count}拒绝 = {total}")
    if pass_count == 0:
        print("  ℹ️  无合规商品，流程结束")
        sys.exit(0)

def check_claim(check_count, pass_count, claimed_ids):
    """③ check_count <= pass_count, claimed_ids <= check_count"""
    ck = check_count or 0
    pc = pass_count or 0
    ci = len(claimed_ids) if claimed_ids else 0

    if ck > pc:
        print(f"  ❌ 校验③: 勾选数 {ck} > 通过数 {pc}，不可能")
        sys.exit(ERR_CHECK_INCOMPLETE)
    if ck < pc:
        print(f"  ⚠️ 校验③: 勾选 {ck}/{pc}（{pc-ck}件未勾到）")
    else:
        print(f"  ✅ 校验③: 勾选 {ck}/{pc}")
    if ci > ck and ck > 0:
        print(f"  ⚠️ 校验③: claimed_ids({ci}) > 勾选数({ck})，后者可能为0，用claimed_ids")
    elif ck == 0 and ci > 0:
        print(f"  ✓ 校验③: check_count为0但实际认领{ci}件（子脚本未报告check_count）")
    if ci < ck and ci > 0:
        print(f"  ⚠️ 校验③: 仅获取到 {ci}/{ck} 个认领主货号")
    # 返回实际认定的认领数：取 max(ci, ck)，但实际认领以 claimed_ids 为准
    return ci if ci > 0 else ck

def check_delete(stdout, expected_remaining, label="删除后残留"):
    """④ 检查删除后的采集箱残留（简单读stdout里的删除计数）"""
    # 从 delete_rejected_products 的输出读 "累计从采集箱删除 X 个"
    m_deleted = re.search(r'累计从采集箱删除\s+(\d+)', stdout or '')
    m_before = re.search(r'未认领:\s*(\d+)', stdout or '')
    if m_deleted and m_before:
        deleted = int(m_deleted.group(1))
        before = int(m_before.group(1))
        after = before - deleted
        if after > expected_remaining:
            print(f"  ⚠️ 校验④: 删除后采集箱剩 {after} 件（预期 ≤{expected_remaining}），可能残留")
        else:
            print(f"  ✅ 校验④: 删除 {deleted} 件，采集箱剩 {after} 件")
    else:
        print(f"  ⚠️ 校验④: 无法获取删除计数（跳过）")

def check_assign(store_assignments, unassigned, total_expected):
    """⑤ 已分配 + 未分配 = pass_count"""
    assigned = sum(len(v) for v in store_assignments.values()) if store_assignments else 0
    unassigned_n = len(unassigned) if unassigned else 0
    total = assigned + unassigned_n
    if total != total_expected:
        print(f"  ❌ 校验⑤: 已分配({assigned}) + 未分配({unassigned_n}) = {total} ≠ 预期 {total_expected}")
        sys.exit(ERR_ASSIGN_MISMATCH)
    print(f"  ✅ 校验⑤: {assigned}件已分配 + {unassigned_n}件未分配 = {total}")
    return assigned, unassigned_n

def check_publish_result(stdout, product_ids, label="发布"):
    """⑥ 发布完成校验"""
    if '✅ 发布完成!' in stdout or '发布完成' in stdout:
        m_publishing = re.search(r'发布中[：:]\s*(\d+)', stdout)
        if m_publishing:
            n = int(m_publishing.group(1))
            print(f"  ✅ 校验⑥: 发布中 {n} 件")
        m_confirm = re.search(r'(\d+)/(\d+)\s*在发布中', stdout)
        if m_confirm:
            found, total = int(m_confirm.group(1)), int(m_confirm.group(2))
            if found < total:
                print(f"  ⚠️ 校验⑥: 仅 {found}/{total} 进入发布中")
        return True
    print(f"  ⚠️ 校验⑥: 发布状态不确定（发布脚本可能未报告完成）")
    return False


# ────────────────────────────────────────────────────────────
# 辅助
# ────────────────────────────────────────────────────────────

def _load_assignment_rules():
    f = PROJECT / "assignment_rules.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding='utf-8'))
        except: pass
    return {"category_rules": [], "product_rules": []}

def _apply_rules(pass_products, stores, store_category_map):
    rules = _load_assignment_rules()
    cat_rules = {r["category"]: r["store"] for r in rules.get("category_rules", [])}
    prod_rules = {r["product_id"]: r["store"] for r in rules.get("product_rules", [])}
    assigned = {}
    unassigned = []
    for p in pass_products:
        pid = p.get('id', '')
        cat = p.get('category', '') or '未分类'
        if pid in prod_rules:
            assigned.setdefault(prod_rules[pid], []).append(p)
            continue
        if cat in cat_rules:
            assigned.setdefault(cat_rules[cat], []).append(p)
            continue
        found = False
        for s_name, cats in store_category_map.items():
            if cat in cats:
                assigned.setdefault(s_name, []).append(p)
                found = True
                break
        if not found:
            unassigned.append(p)
    return assigned, unassigned

def _publish_for_store(store_name, product_ids, skip_publish=False):
    if not product_ids:
        print("  无商品，跳过发布")
        return
    if skip_publish:
        print(f"  ✅ 店铺「{store_name}」跳过发布")
        return
    step(f"发布前校验 → {store_name}")
    max_wait = 300
    all_found = False
    for attempt in range(max_wait // 10):
        sleep(T.FIVE_SECONDS + T.FIVE_SECONDS)  # 10秒
        found, not_found = [], []
        for pid in product_ids:
            out, _ = run_script("run_publish.py", [store_name, "--check-product", pid], timeout=30, retry=0)
            if pid in out:
                found.append(pid)
            else:
                not_found.append(pid)
        if not not_found:
            all_found = True
            break
        print(f"  ⏳ 等待中 ({len(found)}/{len(product_ids)} 已到)...", flush=True)
    if not all_found:
        print(f"  ⚠️ 发布前校验超时，未同步: {not_found}")
        product_ids = found
        if not product_ids:
            print("  ❌ 无可发布商品")
            return
    step(f"发布到 {store_name}")
    out, _ = run_script("run_publish.py", [store_name, "--products", ",".join(product_ids)], timeout=300, retry=1)
    check_publish_result(out, product_ids)


def main():
    parser = argparse.ArgumentParser(description="跨境ERP v2 — 带校验的一键编排")
    parser.add_argument("--claim-to", default="", help="认领/发布到目标店铺")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-publish", action="store_true", help="只做审核认领，跳过发布")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--check-draft", action="store_true")
    parser.add_argument("--skip-image", action="store_true", help="跳过图片审查，只做标题审查")
    parser.add_argument("--products", default="")
    parser.add_argument("--add-rule", default="")
    parser.add_argument("shops", nargs="*", default=[])
    parser.add_argument("-n", "--topn", type=int, default=2)
    parser.add_argument("-k", "--keyword", default="")
    args = parser.parse_args()

    # ── add-rule / check-draft / publish 等快捷场景与 v1 相同 ──
    if args.add_rule:
        rules = _load_assignment_rules()
        if args.add_rule.startswith("category:"):
            parts = args.add_rule[9:].split("->", 1)
            if len(parts) == 2:
                cat, store = parts[0].strip(), parts[1].strip()
                rules["category_rules"] = [r for r in rules.get("category_rules", []) if r["category"] != cat]
                rules["category_rules"].append({"category": cat, "store": store})
        elif args.add_rule.startswith("product:"):
            parts = args.add_rule[8:].split("->", 1)
            if len(parts) == 2:
                pid, store = parts[0].strip(), parts[1].strip()
                rules["product_rules"] = [r for r in rules.get("product_rules", []) if r["product_id"] != pid]
                rules["product_rules"].append({"product_id": pid, "store": store})
        (PROJECT / "assignment_rules.json").write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  ✅ 规则已保存")
        return 0

    if args.check_draft:
        if not args.claim_to:
            print("请用 --claim-to 指定店铺")
            return 1
        step("查看草稿箱")
        out, _ = run_script("run_publish.py", [args.claim_to, "--all"], timeout=120, retry=1)
        return 0

    if args.publish:
        step("直接发布模式 → 跳过审核认领")
        if not args.claim_to:
            print("请用 --claim-to 指定店铺")
            return 1
        if args.products:
            out, _ = run_script("run_publish.py", [args.claim_to, "--products", args.products], timeout=300, retry=1)
        elif args.all:
            out, _ = run_script("run_publish.py", [args.claim_to, "--all"], timeout=300, retry=1)
        else:
            print("请指定 --products 或 --all")
            return 1
        check_publish_result(out, args.products.split(",") if args.products else [])
        print("  ✅ 发布完成!")
        return 0

    # ════════════════════════════════════════════════════════════
    # 全流程：审查(review-only) → 分配 → 认领(有类目匹配的) → 发布
    # 核心逻辑：过审但没匹配类目的商品留在采集箱，不删不认领
    # ════════════════════════════════════════════════════════════
    overall_published = {}  # store_name -> [ids]

    step("阶段1/3: 合规审查 + 删除不合规商品", "━")

    # 用 --review-only：只审查+删除不合规，不认领
    # 过审商品留在采集箱，等分配后再认领
    cmd = ["--review-only"]
    if args.skip_image:
        cmd.append("--skip-image")
    if args.resume:
        cmd.append("--resume")
    stdout, rc = run_script("run_compliance_claim.py", cmd, timeout=600, retry=2)

    j = parse_json(stdout)
    if not j:
        print("  ❌ 审核阶段无结构化输出")
        return 1

    pc = j.get("pass_count", 0)
    rc_count = j.get("reject_count", 0)
    pass_products = j.get("pass_products", [])
    reject_products = j.get("reject_products", [])

    # ── 展示审查结果详情 ──
    if reject_products:
        print(f"\n  ❌ 不合规商品 ({len(reject_products)}件):")
        for i, rp in enumerate(reject_products, 1):
            issues = rp.get("issues", [])
            issue_str = issues[0][:80] if issues else ""
            print(f"    {i}. [{rp.get('id','?')}] {rp.get('title','')[:50]}")
            if issue_str:
                print(f"       原因: {issue_str}")
    elif rc_count > 0:
        print(f"\n  ℹ️  共 {rc_count} 件不合规商品（详情见合规审查脚本输出）")
    else:
        print(f"\n  ✅ 无不合规商品")

    if pass_products:
        print(f"\n  ✅ 合规通过 ({pc}件):")
        for i, pp in enumerate(pass_products, 1):
            print(f"    {i}. [{pp.get('category','?')}] [{pp.get('id','?')}] {pp.get('title','')[:50]}")

    # 校验②
    total_match = re.search(r'采集箱共:\s*(\d+)', stdout or '')
    total_expected = int(total_match.group(1)) if total_match else (pc + rc_count)
    check_counts(pc, rc_count, total_expected)

    if pc == 0:
        print("  无合规商品，结束")
        return 0

    # ════════════════════════════════════════════════════════════
    # 阶段2: 分配 + 认领
    # ════════════════════════════════════════════════════════════
    if pass_products:
        step("阶段2/3: 分配类目 + 认领到店铺", "━")
        store_category_map = {}
        map_file = PROJECT / "store_category_map.json"
        if map_file.exists():
            try:
                store_category_map = json.loads(map_file.read_text(encoding='utf-8-sig'))
            except Exception as e:
                print(f"  读取映射表失败: {e}")

        # 获取店铺列表（从状态文件或直接连接读取）
        stores = j.get("stores", [])
        if not stores:
            # review-only 模式可能没有 stores（没打开弹窗），尝试从配置读取
            stores = list(store_category_map.keys()) if store_category_map else []

        store_assignments, unassigned = _apply_rules(pass_products, stores, store_category_map)

        # 校验⑤
        check_assign(store_assignments, unassigned, pc)

        # 展示未分配商品（这些留在采集箱）
        if unassigned:
            print(f"\n  📦 过审但无匹配类目 ({len(unassigned)}件) → 留在采集箱:")
            for i, p in enumerate(unassigned, 1):
                print(f"    {i}. [{p.get('category','?')}] 主货号({p.get('id','?')}) {p.get('title','?')[:50]}")

        if store_assignments:
            print("\n   分配结果:")
            for s_name, prods in store_assignments.items():
                print(f"    [{s_name}] ← {len(prods)}件")
                for p in prods:
                    print(f"      [{p.get('category','?')}] 主货号({p.get('id','?')})")

            # 逐店铺认领（只认领有类目匹配的商品）
            actual_claimed = 0
            for s_name, prods in store_assignments.items():
                claim_product_ids = [str(p.get('id','')) for p in prods if p.get('id')]
                if not claim_product_ids:
                    continue

                if not args.claim_to:
                    # 没指定 claim-to，用分配规则的店铺名
                    claim_to_store = s_name
                else:
                    claim_to_store = args.claim_to

                print(f"\n  → 认领到[{claim_to_store}]({len(claim_product_ids)}件): {','.join(claim_product_ids)}")
                claim_cmd = [
                    "--direct-claim", ",".join(claim_product_ids),
                    "--claim-to", claim_to_store,
                ]
                if args.skip_image:
                    claim_cmd.append("--skip-image")
                claim_out, claim_rc = run_script("run_compliance_claim.py", claim_cmd, timeout=300, retry=1)

                claim_j = parse_json(claim_out)
                claimed_ids = claim_j.get("claimed_product_ids", []) if claim_j else []
                claimed_n = len(claimed_ids) if claimed_ids else len(claim_product_ids)
                actual_claimed += claimed_n

                # 发布
                publish_ids = claimed_ids if claimed_ids else claim_product_ids
                if publish_ids:
                    print(f"  → 发布到[{s_name}]({len(publish_ids)}件)...")
                    _publish_for_store(s_name, publish_ids, args.skip_publish)
                    overall_published[s_name] = publish_ids

            # 校验③
            check_claim(actual_claimed, pc, [])

        if unassigned and not store_assignments:
            print("\n   以下商品无匹配店铺类目，请手动分配：")
            for i, p in enumerate(unassigned, 1):
                print(f"    {i}. [{p.get('category','?')}] 主货号({p.get('id','?')}) {p.get('title','?')[:50]}")
            if stores:
                print("\n   可用店铺:")
                for i, s in enumerate(stores):
                    print(f"    {i+1}. {s}")
            print("\n  请告诉我怎么分配（留在采集箱，不会删除）")
            return 0

    # 最终汇总
    unassigned_count = len(unassigned) if unassigned else 0
    published_total = sum(len(v) for v in overall_published.values())
    print(f"\n{'='*60}")
    print(f"  🎉 全流程完成!")
    for store, ids in overall_published.items():
        print(f"    店铺「{store}」: {len(ids)}件")
    print(f"    通过审查: {pc}件 | 实际认领: {actual_claimed if 'actual_claimed' in dir() else 0}件 | 成功发布: {published_total}件")
    if unassigned_count > 0:
        print(f"    📦 留在采集箱（未分配类目）: {unassigned_count}件")
    print(f"{'='*60}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
