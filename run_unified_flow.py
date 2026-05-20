#!/usr/bin/env python3
"""V6.0 反爬预留 — 统一采集入口

设计目标：整合 pdd_network.py + pdd_ops.py 的统一采集 CLI。
替代 run_store_collect_flow.py（DrissionPage）和 run_ext_collect.py（扩展按钮）。

用法（占位，V6.0 实现）:
  .venv/bin/python run_unified_flow.py 纳几许大诚专卖店 -n 5

架构:
  run_unified_flow.py  ← CLI入口
    ├── pdd_network.py  ← CDP网络层（拦截+重放）
    └── pdd_ops.py       ← 真人操作层（轨迹+延迟）
"""

import sys


def main():
    print("⚠️ V6.0 统一采集尚未实现")
    print("  当前使用: run_store_collect_flow.py (DrissionPage)")
    print("  或: run_ext_collect.py (扩展按钮方案)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
