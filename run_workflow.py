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
    """运行项目内脚本，返回 stdout。失败时自动重试。"""
    for attempt in range(retry + 1):
        cmd = [sys.executable, name] + args
        print(f"  $ {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                                  encoding='utf-8', errors='replace')
            # 显示输出（缩略模式）
            output = result.stdout
            if len(output) > 1000:
                # 显示最后一千字
                print(output[-1000:])
            else:
                print(output)

            if result.stderr:
                err_lines = [l for l in result.stderr.split('\n')
                            if 'DeprecationWarning' not in l and 'SyntaxWarning' not in l]
                if err_lines:
                    print(f"  stderr: {'; '.join(err_lines[-3:])}")

            if result.returncode == 0:
                return result.stdout, 0

            # 非零退出码，但可能包含 JSON 输出（run_compliance_claim 常返回非零）
            if '--JSON--' in result.stdout:
                return result.stdout, result.returncode

            if attempt < retry:
                print(f"  ⚠️ 退出码 {result.returncode}，{attempt+1}/{retry} 重试...")
                time.sleep(3)
            else:
                return result.stdout, result.returncode

        except subprocess.TimeoutExpired:
            if attempt < retry:
                print(f"  ⚠️ 超时，{attempt+1}/{retry} 重试...")
                time.sleep(3)
            else:
                print(f"  ❌ 超时 {timeout}s")
                return "", -1
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            return "", -1

    return "", -1


def parse_json_output(stdout):
    if "--JSON--" in stdout:
        json_str = stdout.split("--JSON--")[-1].strip()
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    return None


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
    parser.add_argument("--collect", action="store_true", help="【预留】先采集再审核发布")
    parser.add_argument("shops", nargs="*", default=[], help="【预留】PDD店铺名")
    parser.add_argument("-n", "--topn", type=int, default=2, help="【预留】每店采集N件")
    parser.add_argument("-k", "--keyword", default="", help="【预留】店内搜索关键词")
    # ════════════════════════════════════════════════════════
    args = parser.parse_args()

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
    else:
        stdout, rc = run_script("run_compliance_claim.py", [
            "--list-stores"
        ], timeout=600, retry=2)  # 删除失败会重试

    json_data = parse_json_output(stdout)
    if json_data:
        pass_count = json_data.get("pass_count", 0)
        reject_count = json_data.get("reject_count", 0)
        stores = json_data.get("stores", [])
        claimed_ids = json_data.get("claimed_product_ids", [])

        print(f"\n  📊 审核结果:")
        print(f"    通过: {pass_count} 件")
        print(f"    拒绝: {reject_count} 件")

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

        # 认领 — 用户指定了店铺（--claim-to）则自动认领，否则让用户在这里选
        if args.claim_to:
            step(f"阶段2/3: 自动认领到 → {args.claim_to}")
            stdout2, rc2 = run_script("run_compliance_claim.py", [
                "--claim-to", args.claim_to, "--resume"
            ], timeout=300, retry=1)
        else:
            # 在飞书/非交互终端选店铺 — 打出店铺列表让用户在聊天中选
            step("阶段2/3: 选择认领店铺")
            print("\n  ⌛ 可用店铺列表:")
            for i, s in enumerate(stores):
                print(f"    {i+1}. {s}")
            print("\n  ⚠️ 非交互模式，请在聊天中告诉我要选第几个。")
            print(f"  · 说'第一个'或'順順'")
            # 非交互终端下 input() 会 EOFError，直接退出让用户通过参数指定
            print(f"\n  🔄 想继续运行请用:")
            print(f"    python run_workflow.py --claim-to \"店铺名\" --resume")
            print(f"  或直接指定:")
            print(f"    python run_workflow.py --claim-to \"{stores[0]}\" --resume")
            return 0

        json_data2 = parse_json_output(stdout2)
        if json_data2:
            claimed_ids = json_data2.get("claimed_product_ids", [])
            if not claimed_ids:
                claimed_ids = json_data.get("claimed_product_ids", [])
            if claimed_ids:
                print(f"\n  📋 认领主货号 ({len(claimed_ids)}个): {', '.join(claimed_ids)}")
                # 保存到状态文件
                state_file = PROJECT / ".claim_state.json"
                if state_file.exists():
                    try:
                        state = json.loads(state_file.read_text(encoding='utf-8'))
                        state["claimed_product_ids"] = claimed_ids
                        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))
                    except:
                        pass
    else:
        print("  ❌ 审核阶段失败（无结构化输出）")
        return 1

    # ============================================================
    # 阶段3: 发布前轮询校验（认领后商品需要时间同步到发布页）
    # ============================================================
    if args.skip_publish:
        print("\n  ✅ 审核认领完成，跳过发布")
        return 0

    step("阶段3/3: 发布前校验 → 轮询等待发布页出现认领商品")

    publish_ids = args.products
    if not publish_ids:
        state_file = PROJECT / ".claim_state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding='utf-8'))
                if state.get("claimed_product_ids"):
                    publish_ids = ",".join(state["claimed_product_ids"])
            except (json.JSONDecodeError, KeyError):
                pass

    if not publish_ids:
        print("  ⚠️ 无主货号，跳过发布")
        # 检查采集箱是否还有残留
        step("  🔄 清理采集箱残留...")
        run_script("run_compliance_claim.py", ["--delete-rejected"], timeout=120, retry=1)
        return 0

    publish_id_list = publish_ids.split(",")
    print(f"  待发布主货号: {', '.join(publish_id_list)}")
    print(f"  发布主货号: {publish_ids}")

    # 轮询：在发布页搜每个主货号，直到全部出现
    claimed_store = args.claim_to
    import time as _time
    max_wait = 300  # 最多等5分钟
    found_all = False
    for attempt in range(max_wait // 10):
        _time.sleep(10)
        found = []
        not_found = []
        for pid in publish_id_list:
            wait_out, _ = run_script("run_publish.py", [claimed_store, "--check-product", pid], timeout=30, retry=0)
            if pid in wait_out:
                found.append(pid)
            else:
                not_found.append(pid)
        if not not_found:
            found_all = True
            break
        print(f"  ⏳ 等待中 ({len(found)}/{len(publish_id_list)} 已到)...", flush=True)

    if not found_all:
        print(f"  ⚠️ 等待超时，部分商品可能未同步到发布页: {not_found}")
        print(f"  已有 {len(found)}/{len(publish_id_list)} 个，先发布已有的")
        publish_ids = ",".join(found)
        if not publish_ids:
            print("  ❌ 没有可发布的商品")
            return 0

    # 阶段4: 发布
    step("阶段4/4: 发布到 Shopee")
    print(f"  发布主货号: {publish_ids}")
    run_script("run_publish.py", [claimed_store, "--products", publish_ids], timeout=300, retry=1)

    # 清理采集箱：删除残留在采集箱的不合规商品
    step("  🔄 清理采集箱残留...")
    run_script("run_compliance_claim.py", ["--delete-rejected"], timeout=120, retry=1)

    print(f"\n{'='*60}")
    print(f"  🎉 全流程完成!")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
