#!/usr/bin/env python3
"""DeepAgents 编排器 — 跨境ERP全链路工作流

适配 langgraph 1.x

用法:
  python workflow_deepagent.py "采集冠渠旗舰店发到顺顺小屋童装"
  python workflow_deepagent.py --resume "继续"

流程:
  1. 检查ERP登录态
  2. 检查货憨憨插件
  3. 创建 ReAct Agent（6个 Tool + human_confirm 中断）
  4. 执行直至中断或完成
"""

import json
import os
import sys
import subprocess
import traceback
import argparse
from pathlib import Path

from dotenv import load_dotenv

PROJECT = Path(__file__).parent
load_dotenv(PROJECT / ".env")

# ════════════════════════════════════════════════════════════
# Monkey-patch: DeepSeek 推理模型返回 reasoning_content，
# 但新版 LangChain 的 _convert_message_to_dict 会把
# reasoning_content 作为 additional_kwargs 传回 API。
# DeepSeek 要求 reasoning_content 必须原样传回，否则 400。
# 解决方案：从 additional_kwargs 弹出 reasoning_content，
# 放到顶层字段。
# ════════════════════════════════════════════════════════════
import langchain_openai.chat_models.base as _lc_oum
_orig_convert = _lc_oum._convert_message_to_dict

def _patched_convert(message, api="chat/completions"):
    d = _orig_convert(message, api)
    if message.type == "ai":
        rc = message.additional_kwargs.get("reasoning_content")
        if rc:
            d["reasoning_content"] = rc
    return d

_lc_oum._convert_message_to_dict = _patched_convert

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from agent_prompts import PROMPT_MAIN

# ── Config ──
_MODEL_NAME = os.getenv("LLM_TEXT_MODEL", "deepseek-chat")
_LLM_API_KEY = os.getenv("LLM_API_KEY", "")
_LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
_CHECKPOINT_DB = PROJECT / ".checkpoint.db"
_THREAD_FILE = PROJECT / ".last_thread_id"
_INTERRUPT_FILE = PROJECT / ".wf_interrupt.json"

# ============================================================
# 工具函数 — 都是普通函数（非 async），langgraph 1.x 兼容
# ============================================================

def check_hhh_plugin() -> str:
    """检查货憨憨扩展是否注入到当前浏览器"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            from infrastructure.config_loader import ConfigLoader
            _wd_cfg = ConfigLoader().load()
            _wd_port = _wd_cfg.erp_cdp_ports[0]
            b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{_wd_port}")
            page = b.contexts[0].pages[0]
            has = page.evaluate("!!document.querySelector('#hhh-gather-container')")
            return "✅ 货憨憨扩展已激活" if has else "⚠️ 货憨憨扩展未检测到"
    except Exception as e:
        return f"❌ 检查失败: {e}"


def pdd_collect(shop: str, n: int = 3, keyword: str = "") -> str:
    """PDD采集 — 调用 run_store_collect_flow.py

    Args:
        shop: 店铺名
        n: 采集件数
        keyword: 店内搜索关键词
    """
    cmd = [sys.executable, "run_store_collect_flow.py", shop, "-n", str(n)]
    if keyword:
        cmd.extend(["-k", keyword])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace')
        success = result.returncode == 0
        lines = []
        lines.append(f"[RESULT] success={success}, returncode={result.returncode}")
        lines.append("[DETAIL]")
        lines.append(result.stdout[:2000])
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "[RESULT] success=false, error=超时(300s)\n[DETAIL] 采集子进程超时"
    except Exception as e:
        return f"[RESULT] success=false, error={e}\n[DETAIL] 采集子进程异常"


def keyword_collect(keyword: str, n: int = 3, platform: str = "pdd") -> str:
    """按关键词全网搜索采集商品（不需要指定店铺名）

    当用户只说了商品关键词（如"充电宝""裙子""垃圾桶"）但没有说具体哪个店铺时，
    用这个工具按关键词搜索全平台商品并采集。

    Args:
        keyword: 搜索关键词（如"充电宝""垃圾桶""连衣裙"）
        n: 采集件数（默认3）
        platform: 平台（pdd/1688，默认pdd）
    """
    cmd = [sys.executable, "run_ext_collect.py", "-n", str(n), "-k", keyword, "--platform", platform] if keyword else [sys.executable, "run_ext_collect.py", "-n", str(n), "--platform", platform]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace')
        success = result.returncode == 0
        lines = []
        lines.append(f"[RESULT] success={success}, returncode={result.returncode}")
        lines.append("[DETAIL]")
        lines.append(result.stdout[:2000])
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "[RESULT] success=false, error=超时(300s)\n[DETAIL] 关键词采集子进程超时"
    except Exception as e:
        return f"[RESULT] success=false, error={e}\n[DETAIL] 关键词采集子进程异常"


# 全局变量：保存认领成功的主货号列表，供发布步骤用
_CLAIMED_PRODUCT_IDS: list[str] = []

def compliance_claim(target_store: str = "", products: str = "") -> str:
    """合规审查+认领 — 调用 run_compliance_claim.py

    两步流程：
    1. target_store="" → dry-run 列出店铺
    2. target_store="XX" → 认领到指定店铺

    Args:
        target_store: 目标店铺名（空=dry-run）
        products: 逗号分隔的货源ID（空=全部）

    Returns:
        结构化结果字符串，格式:
        [RESULT] success=true/false, pass_count=N, rejected=N, claimed=true/false
        [STORE_LIST] 店铺A,店铺B,店铺C
        [IDS] id1,id2,id3
        [DETAIL] 详细输出...
    """
    global _CLAIMED_PRODUCT_IDS
    if not target_store:
        cmd = [sys.executable, "run_compliance_claim.py", "--list-stores"]
    else:
        cmd = [sys.executable, "run_compliance_claim.py", "--claim-to", target_store]
    if products:
        cmd.extend(["--products", products])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600, encoding='utf-8', errors='replace')
        stdout = result.stdout
        stderr = result.stderr

        # 解析 --JSON-- 结构化数据
        success = False
        pass_count = 0
        reject_count = 0
        claimed = False
        store_list = []
        claimed_ids = []

        if "--JSON--" in stdout:
            json_part = stdout.split("--JSON--")[-1].strip()
            try:
                json_data = json.loads(json_part)
                success = json_data.get("success", False)
                pass_count = json_data.get("pass_count", 0)
                reject_count = json_data.get("reject_count", 0)
                claimed = json_data.get("claimed", False)
                store_list = json_data.get("stores", [])
                claimed_ids = json_data.get("claimed_product_ids", [])
            except (json.JSONDecodeError, KeyError):
                pass

        # 构建结构化返回
        lines = []
        lines.append(f"[RESULT] success={success}, pass_count={pass_count}, rejected={reject_count}, claimed={claimed}")
        if store_list:
            lines.append(f"[STORE_LIST] {','.join(store_list)}")
        if claimed_ids:
            lines.append(f"[IDS] {','.join(claimed_ids)}")
            lines.append(f"⚠️ 认领完成，以上 {len(claimed_ids)} 个主货号请传给 publish_products 的 products 参数精准发布")
            _CLAIMED_PRODUCT_IDS = claimed_ids
        lines.append("[DETAIL]")
        lines.append(stdout[:2000])
        return "\n".join(lines)

    except subprocess.TimeoutExpired:
        return "[RESULT] success=false, error=超时(600s)\n[DETAIL] 合规审查子进程执行超时"
    except Exception as e:
        return f"[RESULT] success=false, error={e}\n[DETAIL] 合规审查子进程异常"


def check_draft_box(store: str) -> str:
    """检查草稿箱 — 返回待发布商品概览

    Args:
        store: 店铺名
    """
    try:
        cmd = [sys.executable, "run_publish.py", store, "--all"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace')
        # 只提取概要
        lines = result.stdout.split("\n")
        summary = [l for l in lines if "草稿箱" in l or "发布成功" in l or "✅" in l or "❌" in l]
        return "\n".join(summary) if summary else result.stdout[:500]
    except Exception as e:
        return f"❌ 草稿箱检查失败: {e}"


def publish_products(store: str, products: str = "") -> str:
    """Shopee发布 — 调用 run_publish.py

    优先使用认领步骤保存的主货号（_CLAIMED_PRODUCT_IDS）精准发布。

    Args:
        store: 目标店铺
        products: 逗号分隔的主货号（空=全部草稿）
    """
    global _CLAIMED_PRODUCT_IDS
    # 🔴 强制只用本轮认领的主货号，禁止 --all 全量发布
    actual_products = products
    if not actual_products and _CLAIMED_PRODUCT_IDS:
        actual_products = ",".join(_CLAIMED_PRODUCT_IDS)
        _CLAIMED_PRODUCT_IDS = []  # 用完后清空
    if not actual_products:
        return "[RESULT] success=false, error=无认领主货号，跳过发布"

    cmd = [sys.executable, "run_publish.py", store, "--products", actual_products]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, encoding='utf-8', errors='replace')
        success = result.returncode == 0
        lines = []
        lines.append(f"[RESULT] success={success}, returncode={result.returncode}")
        lines.append("[DETAIL]")
        lines.append(result.stdout[:2000])
        return "\n".join(lines)
    except Exception as e:
        return f"[RESULT] success=false, error={e}\n[DETAIL] 发布子进程异常"


def human_confirm(stage: str, context: str, options: list[str] = None) -> str:
    """等待人工确认 — 暂停工作流等待用户决策

    调用此工具后工作流暂停，用户通过 --resume 参数传入决策后继续。

    Args:
        stage: 当前阶段名称
        context: 需要确认的内容描述
        options: 可选列表
    """
    msg = f"⏸️ [{stage}] {context[:500]}"
    if options:
        msg += f"\n可选: {', '.join(options)}"
    return msg


def _save_thread_id(tid: str):
    _THREAD_FILE.write_text(tid)


def _load_thread_id() -> str | None:
    if _THREAD_FILE.exists():
        return _THREAD_FILE.read_text().strip()
    return None


def _save_interrupt_info(state):
    try:
        msgs = state.get("messages", [])
        info = []
        for m in msgs[-3:]:
            if hasattr(m, "content") and m.content:
                info.append({
                    "role": getattr(m, "type", "?"),
                    "content": str(m.content)[:300],
                })
        with open(_INTERRUPT_FILE, "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="跨境ERP DeepAgents 编排工作流")
    parser.add_argument("task", nargs="?", default="", help="任务描述")
    parser.add_argument(
        "--resume", nargs="?", const="继续", default=False,
        help="恢复中断的工作流",
    )
    args = parser.parse_args()

    # ── 模型 ──
    model = ChatOpenAI(
        model=_MODEL_NAME,
        api_key=_LLM_API_KEY,
        base_url=_LLM_BASE_URL,
        temperature=0.1,
        max_tokens=8192,
        use_responses_api=False,
    )

    # ── Checkpointer ──
    with SqliteSaver.from_conn_string(str(_CHECKPOINT_DB)) as checkpointer:

        # ── Build Agent ──
        agent = create_react_agent(
            model,
            tools=[
                check_hhh_plugin,
                pdd_collect,
                keyword_collect,
                compliance_claim,
                check_draft_box,
                publish_products,
                human_confirm,
            ],
            prompt=PROMPT_MAIN,
            checkpointer=checkpointer,
        )

        # ── Resume 模式 ──
        if args.resume is not False:
            print("=" * 60)
            print("🔄 恢复工作流（--resume）")
            print("=" * 60)

            thread_id = _load_thread_id()
            if not thread_id:
                print("  ❌ 未找到上次会话 ID，无法恢复")
                return 1

            config = {"configurable": {"thread_id": thread_id}}
            state = agent.get_state(config)

            if not state or not state.values:
                print("  ℹ️  无待恢复的状态")
                return 0

            # 检查是否有中断
            msgs = state.values.get("messages", [])
            has_interrupt = False
            if msgs:
                last = msgs[-1]
                if hasattr(last, "content") and "⏸️" in str(last.content):
                    has_interrupt = True

            if not has_interrupt:
                print("  ℹ️  无待恢复的中断（可能已完成）")
                if msgs:
                    last = msgs[-1]
                    if hasattr(last, "content") and last.content:
                        print(f"\n📋 结果:\n{str(last.content)[:500]}")
                return 0

            resume_value = args.resume if isinstance(args.resume, str) else "继续"
            from langgraph.types import Command
            result = agent.invoke(
                Command(resume=resume_value),
                config=config,
            )

            msgs = result.get("messages", [])
            if msgs:
                last = msgs[-1]
                if hasattr(last, "content") and last.content:
                    print(f"\n📋 结果:\n{str(last.content)[:500]}")
            print("\n✅ 工作流执行完毕")
            return 0

        # ── 新任务模式 ──
        user_input = args.task
        if not user_input:
            print("  ❌ 请输入任务描述")
            print('  用法: python workflow_deepagent.py "采集冠渠旗舰店发到順順の小屋童裝"')
            return 1

        from time import time as _t
        tid = f"erp-{int(_t())}"
        _save_thread_id(tid)
        config = {"configurable": {"thread_id": tid}}

        print("=" * 60)
        print(f"🚀 跨境ERP ReAct 编排器")
        print(f"   会话: {tid}")
        print(f"   任务: {user_input}")
        print("=" * 60)

        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
            )

            msgs = result.get("messages", [])
            if msgs:
                last = msgs[-1]
                if hasattr(last, "content") and last.content:
                    content = str(last.content)
                    if "⏸️" in content:
                        print("\n" + "=" * 60)
                        print("⏸️  工作流已暂停，等待人工确认")
                        print(f"    {content[:500]}")
                        _save_interrupt_info(result)
                        print("\n恢复: workflow_deepagent.py --resume <回复>")
                        print("=" * 60)
                    else:
                        print(f"\n📋 最终结果:\n{content[:1000]}")
                        print("\n✅ 工作流执行完毕")

            return 0

        except KeyboardInterrupt:
            print("\n⚠️ 用户中断")
            return 1
        except Exception as e:
            print(f"\n❌ 异常: {e}")
            traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
