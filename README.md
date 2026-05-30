[![Python](https://img.shields.io/badge/python-3.12-blue?logo=python)]()
[![GitHub last commit](https://img.shields.io/github/last-commit/1060392338/winclaw-erp-workflow)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

# 跨境ERP自动化工作流

> **采集箱审核 → LLM合规审查 + 类目识别 → 按映射表自动分店认领 → Shopee发布**

## 项目结构

```
winclaw-erp-workflow/
├── run_workflow.py              # 一键全流程入口（AI只调这个）
├── run_compliance_claim.py      # 合规审查 + 认领
├── run_publish.py               # Shopee 批量发布
├── store_category_map.json      # 店铺→类目映射表
├── .claim_state.json            # 运行时自动生成（已gitignore）
│
├── config/
│   ├── selectors.py             # ⭐ 集中管理 CSS选择器/UI文案/超时/常量
│   ├── category_list.json       # 类目 + 关键词 + hard_overrides + vision_risk
│   └── config.yaml              # ERP地址/CDP端口/店铺列表
│
├── infrastructure/
│   ├── erp_publisher.py         # ERP操作（采集箱/发布/删除）
│   ├── browser.py               # Playwright CDP 连接
│   ├── compliance_checker.py    # LLM合规审查
│   ├── image_checker.py         # OCR + Vision 图片审查
│   ├── taiwan_regulation.py     # 台湾广告法+政治敏感审查
│   ├── title_optimizer.py       # 标题优化
│   ├── llm_client.py            # 统一 LLM 封装
│   └── config_loader.py         # 配置加载
│
├── models/
│   └── schema.py                # 数据模型
├── .env                         # API Key（已gitignore）
└── requirements.txt             # Python 依赖
```

## 📖 从零配置

完整配置步骤见 **[SETUP_NEW_PC.md](SETUP_NEW_PC.md)**：
1. Python 3.12 + Chrome
2. 获取 DeepSeek + 阿里百炼 API Key
3. 配置 `config/config.yaml` + `store_category_map.json`
4. 启动 Chrome + 登录 ERP
5. 一键运行

## 🚀 一键全流程

```powershell
# 清状态 + 全流程（审查→认领→发布）
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "吉象星連坊（本土）"

# 跳过图片审查（API额度不足）
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "吉象星連坊（本土）" --skip-image

# 按类目自动分配（需配好 store_category_map.json）
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py
```

## 🔧 全流程说明

```
阶段1: 合规审查
  run_compliance_claim.py --review-only
  → 采集箱全量扫描 → LLM审查（标题+图片） → 不合规自动删除 → 过审商品留采集箱

阶段2: 分配 + 认领
  → run_workflow.py 按映射表分配类目
  → run_compliance_claim.py --direct-claim ID列表 --claim-to 店铺
  → 逐页扫描认领（claim-and-replace循环）

阶段3: 发布
  → run_publish.py 店铺名 --products ID列表
  → 跨页循环勾选+发布
```

## 💡 核心策略

- **Claim-and-Replace 循环认领**：单页≤20快速通道，多页逐页扫描，翻页后翻回第1页重勾选
- **config/selectors.py 集中管理**：SEL=CSS选择器/TXT=UI文案/T=超时/C=常量
- **hard_overrides 硬规则**：关键词强制类目映射（刀→家居）
- **vision_risk 分级**：低风险类目跳过 Vision 审查

## 📦 环境依赖

- **Python 3.12**
- **Chrome**（`--remote-debugging-port=9223`）
- **依赖**：`pip install -r requirements.txt`
- **Tesseract OCR**（可选，推荐）：详见 SETUP_NEW_PC.md
- **模型**：DeepSeek（文字）+ 阿里百炼 qwen3-vl-plus（图片）
