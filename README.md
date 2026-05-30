[![Python](https://img.shields.io/badge/python-3.12-blue?logo=python)]()
[![GitHub last commit](https://img.shields.io/github/last-commit/1060392338/winclaw-erp-workflow)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

# 跨境ERP自动化工作流

> **采集箱审核 → LLM 合规审查（标题） → 类目识别 → 按映射表自动分店认领 → Shopee 发布**

## 项目结构

```
winclaw-erp-workflow/
├── run_workflow.py              # 一键全流程入口（AI 只调这个）
├── run_compliance_claim.py      # 合规审查 + 认领
├── run_publish.py               # Shopee 批量发布
├── store_category_map.json      # 店铺→类目映射表
├── tessdata/                    # OCR 中文语言包（chi_sim/chi_tra/eng）
│
├── config/
│   ├── selectors.py             # ⭐ 集中管理 CSS选择器/UI文案/超时/常量
│   ├── category_list.json       # 类目 + 关键词 + hard_overrides + vision_risk
│   └── config.yaml              # ERP地址/CDP端口/店铺列表
│
├── infrastructure/
│   ├── erp_publisher.py         # ERP操作（采集箱/发布/删除）
│   ├── browser.py               # Playwright CDP 连接
│   ├── compliance_checker.py    # LLM合规审查（标题+类目单次调用）
│   ├── image_checker.py         # OCR + Vision 图片审查
│   ├── taiwan_regulation.py     # 台湾广告法+政治敏感关键词规则
│   ├── title_optimizer.py       # 标题优化
│   ├── llm_client.py            # 统一 LLM 封装（支持 chat + chat_json）
│   └── config_loader.py         # 配置加载
│
├── models/
│   └── schema.py                # 数据模型（Product / ComplianceResult）
├── .env                         # API Key（已 gitignore）
├── requirements.txt             # Python 依赖
├── SETUP_NEW_PC.md              # 📖 完整配置指引（从零开始）
└── SKILL.md                     # 🤖 AI 智能体操作手册
```

## 🚀 一键全流程

```powershell
# 清状态 + 全流程（跳过图片审查，推荐）
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "吉象星連坊（本土）" --skip-image

# 含图片审查（需要阿里百炼 API Key）
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "吉象星連坊（本土）"

# 按类目自动分配到对应店铺（需配好 store_category_map.json）
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py
```

## 📖 文档

| 文档 | 阅读对象 | 内容 |
|------|---------|------|
| [SETUP_NEW_PC.md](SETUP_NEW_PC.md) | 真人操作者 | 从零配置环境、API Key、店铺、Chrome |
| [SKILL.md](SKILL.md) | AI 智能体 | 操作决策树、已知 Bug、故障排查 |
| README.md（本文） | 所有人 | 项目概览 + 快速上手 |

## 🔧 全流程说明

```
阶段1: 合规审查
  run_compliance_claim.py --review-only
  → 采集箱全量扫描 → LLM审查（标题，单次调用同时返回合规+类目）
  → 不合规商品自动删除 → 过审商品留采集箱

阶段2: 分配 + 认领
  → run_workflow.py 按映射表分配类目
  → run_compliance_claim.py --direct-claim --claim-to 店铺
  → 单页快速通道 / 多页 claim-and-replace 循环

阶段3: 发布
  → run_publish.py 店铺名 --products ID列表
  → claim-and-replace 循环勾选+弹窗自动处理
```

## 💡 核心策略

- **Claim-and-Replace 循环认领**：单页≤20快速通道，多页逐页扫描，翻页后翻回第1页重勾选
- **LLM 单次调用审查+类目**：合并标题审查和类目识别为一次 LLM 调用，减少 50% API 时间
- **config/selectors.py 集中管理**：SEL=CSS选择器 / TXT=UI文案 / T=超时 / C=常量
- **hard_overrides 硬规则**：关键词强制类目映射（刀→家居、碗→家居）
- **Vue Recycle Scroller 适配**：逐格 scrollTo + sleep(80ms)，确保每行都被渲染

## 📦 环境依赖

- **Python 3.12**
- **Chrome**（`--remote-debugging-port=9223`）
- **依赖**：`pip install -r requirements.txt`
- **Tesseract OCR**（可选，推荐安装）
- **模型**：DeepSeek（文字）+ 阿里百炼 qwen3-vl-plus（图片）
