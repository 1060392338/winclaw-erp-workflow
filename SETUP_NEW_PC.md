# 新电脑部署指南 — 跨境ERP自动化工作流

> 📌 **本指南同时面向两类读者：**
> - **真人操作者**：跟着步骤装环境、配 Key、登录 ERP，然后跑起来
> - **AI 智能体**：文档说明了系统运行所需的所有依赖、环境、配置文件和业务逻辑

---

## 一、项目概述

**这个项目做什么？**
ERP 采集箱商品 → LLM 合规审查（标题+图片） → 类目识别 → 按店铺→类目映射表分配 → 认领到指定店铺 → 发布到 Shopee

**核心脚本：**
| 脚本 | 作用 |
|------|------|
| `run_workflow.py` | **一键全流程入口**（AI 只调这个就行） |
| `run_compliance_claim.py` | 合规审查 + 认领（--review-only 只审不认，--direct-claim 直接认领） |
| `run_publish.py` | Shopee 批量发布（跨页循环勾选+弹窗处理） |

**配置文件（AI 必须知道）：**
| 文件 | 作用 |
|------|------|
| `.env` | API Key（DeepSeek + 阿里百炼），已 gitignore |
| `config/config.yaml` | ERP 地址、CDP 端口、店铺列表 |
| `config/selectors.py` | **所有 CSS 选择器、UI 文案、超时参数集中管理**。ERP 升级或改 UI 只需改此文件 |
| `config/category_list.json` | 类目列表 + 关键词映射 + hard_overrides（硬规则） + vision_risk 配置 |
| `store_category_map.json` | 店铺→可分配类目的映射表，决定商品认领到哪个店 |
| `.claim_state.json` | 运行时自动生成，记录上次审查结果（已 gitignore） |

---

## 二、环境准备（5分钟）

### 2.1 Python 3.12+

```powershell
python --version
# 输出 >= 3.12
```

### 2.2 Chrome 浏览器（最新版）

已有则跳过，没有去 https://www.google.com/chrome/ 下载。

---

## 三、下载项目（2分钟）

```powershell
cd C:\Users\Administrator\Desktop
git clone https://github.com/1060392338/winclaw-erp-workflow.git winclaw-erp-workflow
cd winclaw-erp-workflow
```

---

## 四、安装依赖（5分钟）

### 4.1 Python 依赖

```powershell
pip install -r requirements.txt
playwright install chromium
```

如果 `pip install` 报错，手动装：
```powershell
pip install playwright requests pyyaml python-dotenv openai langchain-openai langchain-core pytesseract Pillow
playwright install chromium
```

### 4.2 Tesseract OCR（可选，推荐安装）

OCR 加速图片文字识别，不装也能跑（走纯 LLM Vision 兜底，更慢更贵）。

**安装方式：**
```powershell
winget install UB-Mannheim.TesseractOCR
```

安装后验证：
```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

**中文语言包安装（已下载到 `C:\Users\Administrator\tessdata\`）：**
```powershell
# 如果未下载，从 GitHub 下载：
# chi_sim.traineddata (42MB) — 简体中文
# chi_tra.traineddata (56MB) — 繁体中文
# 存放在 C:\Users\Administrator\tessdata\ 目录
```

> ⚠️ `image_checker.py` 自动检测 `~/tessdata/` 和 `C:\Program Files\Tesseract-OCR\tessdata\`，不用额外配置。

---

## 五、配置 API Key（必做，3分钟）

### 5.1 获取 API Key

**① DeepSeek（文字模型，合规审查 + 标题优化）**
- https://platform.deepseek.com/api_keys
- 创建 API Key → 充值（$5 能用很久）

**② 阿里百炼 DashScope（图片识别，Vision 审查）**
- https://bailian.console.aliyun.com
- API Key 管理 → 创建 API Key
- 需要开通「百炼」服务并有 qwen3.6-plus（或 qwen3-vl-plus）调用权限

### 5.2 填入 .env

复制 `.env.example` 为 `.env`：

```powershell
cp .env.example .env
notepad .env
```

**填好后应类似：**

```env
# === DeepSeek 文字模型 ===
LLM_API_KEY=sk-你的DeepSeekKey
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-chat
LLM_LIGHT_MODEL=deepseek-v4-flash

# === 阿里百炼 视觉模型 ===
VISION_API_KEY=sk-你的阿里百炼Key
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_IMAGE_MODEL=qwen3-vl-plus
```

> ⚠️ `.env` 已在 `.gitignore` 中，不会提交到 GitHub。

### 5.3 验证 API Key

```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
from openai import OpenAI; import os; from dotenv import load_dotenv
load_dotenv()
c = OpenAI(api_key=os.environ.get('LLM_API_KEY'), base_url=os.environ.get('LLM_BASE_URL'))
r = c.chat.completions.create(model='deepseek-chat', messages=[{'role':'user','content':'hi'}], max_tokens=10)
print('文字模型 OK:', r.choices[0].message.content)
"
```

---

## 六、配置店铺（必做，2分钟）

### 6.1 修改 config/config.yaml

把 `stores` 换成你 ERP 账号下实际的店铺名。

```yaml
stores:
  - id: "store_1"
    name: "你的店铺名（含括号）"    # ← 必须和ERP弹窗完全一致
    platform: "Shopee"
    region: "TW"
```

怎么知道店铺名？登录 ERP → 认领弹窗会列出所有店铺。

### 6.2 配置店铺类目映射表（强烈推荐）

编辑 `store_category_map.json`：

```json
{
  "吉象星連坊（本土）": ["童裝", "五金", "家居", "其他"],
  "另一个店铺": ["百货", "母婴"]
}
```

**规则：**
- 店铺名必须与 ERP 认领弹窗**完全一致**（含括号、全半角）
- 类目由 LLM 自动识别，支持：童裝、五金、百货、3C、服装、食品、美妆、家居、母婴、户外、宠物、其他
- 配了类目的 → 该店只会收到匹配类目的商品
- 留空 `[]` → 该店不会收到任何商品
- 不在映射表中的类目 → 合规商品留在采集箱（不会删除）

---

## 七、启动 Chrome + 登录 ERP（必做，3分钟）

### 7.1 以调试模式启动 Chrome

```powershell
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --remote-allow-origins=*
```

### 7.2 验证端口

```powershell
curl -s http://127.0.0.1:9223/json/version | head -5
# 有 JSON 返回说明成功
```

### 7.3 登录 ERP

1. 在该 Chrome 窗口访问 https://www.huohanhan.com
2. 登录（手机号+密码+图形验证码）
3. 确认能打开采集箱：https://www.huohanhan.com/member/product/general/collect-box
4. **保持 Chrome 窗口打开，不要关闭！**

> ⚠️ ERP Session 跨天过期，需重新登录。

---

## 八、一键运行（1分钟）

### 方案 A：全部认领到一个店铺（推荐首次使用）

```powershell
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "吉象星連坊（本土）"
```

### 方案 B：跳过图片审查（API 额度不足时）

```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "吉象星連坊（本土）" --skip-image
```

### 方案 C：按类目自动分配（需配好映射表）

```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py
```

---

## 九、全流程内部逻辑（AI 必读）

```
阶段1: 合规审查
  └─ run_compliance_claim.py --review-only
      ├─ 采集箱全量扫描（跨页+虚拟滚动展开）
      ├─ LLM 审查（标题+图片，并发5线程）
      ├─ 不合规商品自动删除（循环法+展开页面触发渲染）
      └─ 过审商品留在采集箱，等待分配

阶段2: 分配 + 认领
  ├─ run_workflow.py 根据 store_category_map.json 分配类目
  └─ run_compliance_claim.py --direct-claim ID列表 --claim-to 店铺
      └─ 逐页扫描认领（动态分页处理+翻回第1页重试勾选）

阶段3: 发布
  └─ run_publish.py 店铺名 --products ID列表
      └─ claim-and-replace 循环勾选+发布（草稿箱45→36，发布中0→9）
```

### 核心策略说明

**Claim-and-Replace 循环认领：**
- 单页（≤20件）：快速通道，一次勾选认领
- 多页（>20件）：逐页扫描
  - 第1页有匹配 → 勾选认领
  - 第1页无匹配 → 翻到第2页找 → 找到后翻回第1页重新勾选认领
  - 认领按钮在第2+页不可用时 → 自动翻回第1页重试+重新勾选

**页面文档配置（config/selectors.py）**
所有 CSS 选择器、UI 文案、超时参数集中管理在 `config/selectors.py` 中：
- `SEL.*` — CSS 选择器（dialog/tab/table/button/pagination）
- `TXT.*` — UI 文案（tab名/按钮文本/label）
- `T.*` — 超时参数（毫秒）
- `C.*` — 常量（PAGE_SIZE=20/扩高值/滚动步长）
- 辅助函数：close_dialogs()/switch_tab()/expand_and_scroll()/sleep()

---

## 十、验证清单

| # | 项目 | 检查方式 |
|---|------|----------|
| 1 | Python 3.12 | `python --version` |
| 2 | Chrome 已启动 | 有 Chrome 窗口 |
| 3 | Chrome CDP 端口 | `curl -s http://127.0.0.1:9223/json/version` 有返回 |
| 4 | ERP 已登录 | 采集箱能看到「未认领」tab |
| 5 | OCR 可选 | `python -c "import pytesseract; print('OK')"` |
| 6 | `.env` 已配 | `Get-Content .env` 有 API Key |
| 7 | API Key 有效 | 第五章验证命令通过 |
| 8 | `config/config.yaml` 已改 | 店铺名是真实名 |
| 9 | `store_category_map.json` 已配 | 已配置至少一个店铺 |
| 10 | 依赖完整 | `python run_workflow.py --help` 有输出 |

---

## 十一、常见问题

### 编码错误
```powershell
$env:PYTHONIOENCODING='utf-8'
```

### Chrome 连不上
→ 确认已用 `--remote-debugging-port=9223` 启动

### 找不到店铺
→ 店铺名和弹窗不一致，检查 `config/config.yaml` 和 `store_category_map.json`

### 全部被拒绝
→ 可能是采集箱没有未认领商品，或所有商品都违规

### 认领后发布确认=0
→ 认领后需等几十秒同步到发布页，代码会自动轮询
