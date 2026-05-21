---
name: cross-border-erp-automation
description: 跨境电商ERP自动化 — `run_workflow.py` 一键全流程。采集箱审核→LLM合规→类目识别→按映射表分店→Shopee发布。
---

# 跨境ERP自动化

**项目路径**: `C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\`
**Python**: 3.12，无虚拟环境

## 死命令

1. 跑前 `Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue`
2. 编码前缀 `$env:PYTHONIOENCODING='utf-8'`
3. 货源ID = 主货号（值一样叫法不同）

## 入口命令

```powershell
# 全流程（指定店）
python run_workflow.py --claim-to "順順の小屋童裝（本土）"

# 全流程（自动分配）
python run_workflow.py

# 只审核
python run_workflow.py --claim-to "店名" --skip-publish

# 直接发布
python run_workflow.py --claim-to "店名" --publish --products id1,id2
```

## 映射表（当前）

```json
{
  "順順の小屋童裝（本土）": [
    "童裝",
    "五金"
  ],
  "吉象星連坊（本土）": [],
  "zhuangjiaen_（本土）": []
}
```

## 脚本列表

| 文件 | 功能 |
|------|------|
| `run_workflow.py` | 一键全流程入口 |
| `run_compliance_claim.py` | 审查+认领 |
| `run_publish.py` | 精准发布（弹窗双路径）|
| `store_category_map.json` | 类目分配表 |
