---
name: cross-border-erp-automation
description: 跨境电商ERP自动化 — 采集箱审核→LLM合规→货憨憨认领→Shopee发布。`run_workflow.py` 一键全流程。
---

# 跨境ERP自动化

## 项目路径

`C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\`
Python 3.12，无虚拟环境。

## 🔴 死命令

1. **跑前清空状态文件**：
   ```powershell
   Remove-Item -Force .claim_state.json, .preferred_store -ErrorAction SilentlyContinue
   ```
2. **入口：`run_workflow.py`**
3. **类目分配**：按 `store_category_map.json` 自动分配。不匹配的留采集箱不动。
4. **货源ID = 主货号**，发布后看发布中/发布成功/发布失败 tab 确认。

## 当前映射表

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

## 常用命令

```powershell
# 清状态 + 跑全流程（指定店铺）
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "順順の小屋童裝（本土）"

# 自动按类目分配
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py

# 添加分配规则
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --add-rule "category:童裝->順順の小屋童裝（本土）"

# 直接发布
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --products id1,id2

# 只审核不发布
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --skip-publish
```

## 环境依赖

- **Python 3.12**
- **Chrome**（`--remote-debugging-port=9223`）
- **依赖**：`pip install playwright requests pyyaml python-dotenv Pillow`
- **模型**：.env 中配置（当前 image=qwen3.6-plus, light=deepseek-v4-flash）
