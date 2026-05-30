# 新电脑部署指南 — 跨境ERP自动化工作流

> **本指南同时面向两类读者：**
> - **真人操作者**：跟着步骤装环境、配 Key、登录 ERP，然后跑起来
> - **AI 智能体**：这是系统的完整技术档案。如果 AI 操作时卡住了，回这里查环境依赖和配置细节

---

## 一、项目概述

**这个项目做什么？**
ERP 采集箱商品 → LLM 合规审查（标题识别） → 类目识别 → 按店铺-类目映射表分配 → 认领到指定店铺 → 发布到 Shopee

**一句话：从采集箱到上线，全自动。**

### 核心脚本

| 脚本 | 作用 | 调用方式 |
|------|------|----------|
| `run_workflow.py` | **一键全流程入口**（AI 智能体只调这个） | `python run_workflow.py --claim-to "店名"` |
| `run_compliance_claim.py` | 合规审查 + 认领 | 由 workflow 自动调用 |
| `run_publish.py` | Shopee 批量发布 | 由 workflow 自动调用 |

### 关键配置文件

| 文件 | 作用 | 是否需要用户编辑 |
|------|------|-----------------|
| `.env` | API Key（DeepSeek + 阿里百炼） | ✅ **必配** |
| `config/config.yaml` | ERP 地址、CDP 端口、店铺列表 | ✅ **必配** |
| `config/selectors.py` | CSS 选择器 / UI 文案 / 超时 / 常量 — **集中管理** | ⬜ 不改则用默认 |
| `config/category_list.json` | 类目列表 + 关键词 + hard_overrides | ⬜ 不改则用默认 |
| `store_category_map.json` | 店铺→类目映射表 | ✅ **推荐配置** |
| `.claim_state.json` | 运行时自动生成（已 gitignore） | ❌ 自动，不用管 |

---

## 二、环境准备

### 2.1 Python 3.12

```powershell
# 确认版本（用完整路径避免多版本冲突）
& "C:\Program Files\Python312\python.exe" --version
# 输出应为 Python 3.12.x
```

如果还没有 Python 3.12，去 https://www.python.org/downloads/ 下载 **Python 3.12.x**。

> ⚠️ 必须是 3.12 系列。后续所有命令中请用 `& "C:\Program Files\Python312\python.exe"` 而非裸 `python`。

### 2.2 Chrome 浏览器（最新版）

已有则跳过，没有去 https://www.google.com/chrome/ 下载。

### 2.3 Git

```powershell
git --version
# 输出应为 git version 2.x
```

---

## 三、下载项目

```powershell
cd C:\Users\Administrator\Desktop
git clone https://github.com/1060392338/winclaw-erp-workflow.git
cd winclaw-erp-workflow
```

---

## 四、安装依赖

### 4.1 Python 依赖

```powershell
pip install -r requirements.txt
playwright install chromium
```

如果 `pip install` 报错，可逐一手动安装：

```powershell
pip install playwright requests pyyaml python-dotenv pydantic openai pyperclip
playwright install chromium
```

### 4.2 Tesseract OCR（可选，但推荐）

OCR 加速图片文字识别。不装也能跑（走纯 LLM Vision 兜底，更慢更贵）。

```powershell
winget install UB-Mannheim.TesseractOCR
```

安装后验证：

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
```

**中文语言包：**

下载以下文件到项目 `tessdata\` 目录：

```powershell
cd C:\Users\Administrator\Desktop\winclaw-erp-workflow
mkdir -Force tessdata
# 从 https://github.com/tesseract-ocr/tessdata 下载：
#   chi_sim.traineddata (~43MB) — 简体中文
#   chi_tra.traineddata (~57MB) — 繁体中文
#   eng.traineddata (~4MB) — 英文
# 放入 tessdata\ 目录
```

> `image_checker.py` 自动按 **项目目录 → 用户目录 → 安装目录** 三级优先查找 tessdata，不用额外配置。

---

## 五、配置 API Key

### 5.1 获取 API Key

**① DeepSeek（文字模型 — 标题审查 + 类目识别）**
- 注册：https://platform.deepseek.com
- 创建 API Key：https://platform.deepseek.com/api_keys
- 充值：建议先充 $5（够跑几百次）

**② 阿里百炼 DashScope（图片识别 — Vision 审查）**
- 开通：https://bailian.console.aliyun.com
- 创建 API Key：API Key 管理
- 需要开通「百炼」服务并有 `qwen3-vl-plus` 调用权限

### 5.2 填入 .env

复制并编辑：

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

> ⚠️ `.env` 已在 `.gitignore` 中，不会提交到 GitHub。但操作时注意不要在聊天中直接粘贴 API Key。

### 5.3 验证 API Key

```powershell
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" -c "
from openai import OpenAI; import os; from dotenv import load_dotenv
load_dotenv()
c = OpenAI(api_key=os.environ.get('LLM_API_KEY'), base_url=os.environ.get('LLM_BASE_URL'))
r = c.chat.completions.create(model='deepseek-chat', messages=[{'role':'user','content':'hi'}], max_tokens=10)
print('✅ 文字模型 OK:', r.choices[0].message.content)
"
```

---

## 六、了解系统支持的类目（首次必读）

系统通过 LLM 自动识别商品类目。**这是整个映射系统的基础**——你先看下面支持哪些类目，再决定你的店铺要接入哪些。

### 6.1 预设类目清单

打开 `config/category_list.json`，你会看到以下预置类目：

| 类目 | 适用商品示例 | vision_risk（图片审查等级） |
|------|-------------|--------------------------|
| **童裝** | 婴儿、儿童、童装、幼儿园 | medium |
| **五金** | 螺丝、扳手、铰链 | low（可跳过图片审查） |
| **百货** | 收纳、挂钩、置物架 | low |
| **3C** | 手机、耳机、充电器 | low |
| **服装** | T恤、衬衫、牛仔裤 | high（必须图片审查） |
| **食品** | 零食、茶叶、坚果 | high |
| **美妆** | 面膜、口红、粉底 | high |
| **家居** | 碗、刀、锅、收纳 | low |
| **母婴** | 奶瓶、纸尿裤、推车 | high |
| **户外** | 帐篷、登山、运动 | low |
| **宠物** | 猫粮、狗粮、猫砂 | low |
| **其他** | — | medium |

> **vision_risk 说明：** `low`=OCR通过后可跳过 AI Vision 审查（更快更省），`high`=必须走 AI Vision（更严格）。

### 6.2 自定义类目（可选）

如果需要添加新类目，编辑 `config/category_list.json`：

```json
{
  "categories": ["童裝", "五金", "百货", ... , "你新增的类目"],
  "keywords": {
    "你新增的类目": ["关键词1", "关键词2"]
  },
  "vision_risk": {
    "你新增的类目": "low"
  },
  "hard_overrides": {
    "关键词": "你新增的类目"
  }
}
```

**编辑完成后再继续下面步骤。**

---

## 七、启动 Chrome + 登录 ERP（查看店铺）

> ⚠️ **必须先登录 ERP 才能看到你的店铺！** 下面的配置步骤需要你在 ERP 里查看店铺名。

### 7.1 以调试模式启动 Chrome

```powershell
# 如果已有关闭所有 Chrome 窗口，然后执行：
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --remote-allow-origins=*
```

> ⚠️ 必须用 `--remote-debugging-port=9223`，否则脚本连不上。

### 7.2 验证端口

```powershell
curl -s http://127.0.0.1:9223/json/version | head -5
```

有 JSON 返回说明成功。

### 7.3 登录 ERP

1. 在刚启动的 Chrome 窗口访问 **https://www.huohanhan.com**
2. 登录（手机号+密码+图形验证码）
3. 确认能打开采集箱：https://www.huohanhan.com/member/product/general/collect-box
4. 能看到「未认领」tab 且有商品
5. **保持 Chrome 窗口打开，不要关闭！**

> ⚠️ ERP Session 跨天过期，需重新登录。

### 7.4 查看你的店铺列表

保持 Chrome 窗口开着，执行以下命令查看 ERP 认领弹窗中列出的店铺：

```powershell
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" -c "
import sys; sys.path.insert(0, '.')
from infrastructure.config_loader import ConfigLoader
from infrastructure.browser import BrowserManager
import time

try:
    bm = BrowserManager(); bm.connect(); page = bm.page
    cfg = ConfigLoader().load()
    page.goto(f'{cfg.erp_url}/member/product/general/collect-box', wait_until='domcontentloaded', timeout=60000)
    time.sleep(2)
    page.wait_for_load_state('networkidle', timeout=30000)
    # 关弹窗
    page.evaluate('() => { document.querySelectorAll(\"[class*=\"dialog\"]\").forEach(d => { const c = d.querySelector(\"[class*=\"close\"]\"); if(c && typeof c.click === \"function\") c.click(); }); }')
    time.sleep(1)
    # 切未认领tab
    page.evaluate('(sel) => { const tabs = document.querySelectorAll(sel); for(const t of tabs) { if(t.textContent.match(/未认领|鏈棰?/)) { t.click(); return; } } }', '[class*=\"t-tab\"],[class*=\"radio-button\"]')
    time.sleep(2)
    # 勾选任意商品 → 点认领 → 读弹窗店铺
    cbs = page.evaluate('() => { return document.querySelectorAll(\"input[type=checkbox]\").length; }')
    if cbs == 0:
        print('❌ 采集箱无商品，无法读取店铺列表。请先确认ERP上有未认领商品。')
        sys.exit(1)
    page.evaluate('() => { const cb = document.querySelector(\"input[type=checkbox]\"); if(cb && !cb.checked) cb.click(); }')
    time.sleep(1)
    page.evaluate('(t) => { const btns = document.querySelectorAll(\"button\"); for(const b of btns) { if(b.textContent.includes(t)) { b.click(); return; } } }', '认领')
    time.sleep(3)
    stores = page.evaluate('() => { const items = document.querySelectorAll(\"[class*=\"select-block-item\"]\"); return Array.from(items).map(el => el.textContent.trim()).filter(Boolean); }')
    if stores:
        print(f'你的ERP店铺列表 ({len(stores)}个):')
        for i, s in enumerate(stores, 1):
            print(f'  {i}. {s}')
    else:
        print('❌ 未读取到店铺列表，认领弹窗可能未正常弹出。')
    # 关弹窗
    page.evaluate('() => { document.querySelectorAll(\".t-dialog__close\").forEach(c => { if(c.offsetParent !== null && typeof c.click === \"function\") c.click(); }); }')
except Exception as e:
    print(f'❌ 执行出错: {e}')
    print('  请确认: ① Chrome已用--remote-debugging-port=9223启动')
    print('          ② ERP已登录且采集箱有未认领商品')
    print('          ③ 没有弹窗遮挡页面')
"
```

输出示例：
```
你的ERP店铺列表:
  1. 吉象星連坊（本土）
  2. zhuangjiaen_（本土）
```

> **记下这些店铺名**（含括号和全半角），下一步要用。

---

## 八、配置店铺和类目映射

> 现在你已经知道：
> - ✅ 系统支持哪些类目（第六步）
> - ✅ 你的 ERP 有哪些店铺（第七步）
> 
> 接下来就是把它们对应起来。

### 8.1 编辑 config/config.yaml

`config/config.yaml` 已自带完整模板，你只需改 `stores` 部分（店铺名和数量）：

```yaml
# ERP 地址（不常改）
erp:
  url: "https://www.huohanhan.com"
  cdp_ports:
    - 9223

# ⬇⬇⬇ 把这里换成你的店铺 ⬇⬇⬇
stores:
  - id: "store_1"
    name: "吉象星連坊（本土）"    # ← 第7.4步扫描到的店铺名
    platform: "Shopee"
    region: "TW"
  - id: "store_2"                  # 如果有第二个店铺就这样加
    name: "zhuangjiaen_（本土）"
    platform: "Shopee"
    region: "TW"
  # 更多店铺照这个格式往下加即可

# 以下部分保持默认，不用动
browser:
  chrome_path: ""
  remote_debugging_ports: [9223]
runtime:
  platform: "openclaw"
llm:
  image_model: "qwen3-vl-plus"
  text_model: "deepseek-v4-flash"
```

> ⚠️ **店铺名**必须与第 7.4 步扫描出来的**完全一致**（含括号、全半角）。`（本土）` ≠ `(本土)`。

### 8.2 配置店铺类目映射表（核心）

编辑 `store_category_map.json`，把第七步看到的店铺和第六步了解到的类目对应起来：

```json
{
  "吉象星連坊（本土）": ["童裝", "五金", "家居", "其他"],
  "zhuangjiaen_（本土）": ["百货", "母婴", "户外"]
}
```

**规则说明：**
| 场景 | 写法 | 结果 |
|------|------|------|
| 只卖特定类目 | `"店名": ["童裝", "五金"]` | 只认领童装和五金类商品 |
| 全部类目都收 | `"店名": ["童裝","五金","百货","3C","服装","食品","美妆","家居","母婴","户外","宠物","其他"]` | 所有类目全认领 |
| 该店不接商品 | `"店名": []` | 该店不认领任何商品 |
| 不在列表中的类目 | — | 合规但无映射 → 留在采集箱 |

> 💡 **快速全选**：直接复制上面「全部类目都收」的数组即可。

> ⚠️ **店铺名必须与 ERP 弹窗完全一致**，含括号、全半角。`（本土）` 不等于 `(本土)`。

---

## 🔧 九、疑难排解

### 编码错误
```powershell
# 所有命令前加这个
$env:PYTHONIOENCODING='utf-8'
```
原因：Windows PowerShell 默认 GBK 编码，不兼容 emoji（🔍❌✅ 等）。

### Chrome 连不上
```
错误信息：CDP connection failed / 连接被拒绝
```
→ 确认 Chrome 已用 `--remote-debugging-port=9223` 启动
→ 验证：`curl -s http://127.0.0.1:9223/json/version`

### 找不到店铺
```
错误信息：❌ 未找到目标店铺 'xxx'
```
→ 检查 `store_category_map.json` 中的店名与 ERP 弹窗**完全一致**
→ 注意全角/半角括号：`（本土）` ≠ `(本土)`

### 审查结果全 PASS（含明显违规品）
```
现象：宝可梦、凯蒂猫等 IP 侵权商品全部 pass
```
→ 原因：`LLMClient.chat()` 不支持 `response_format` 参数，LLM 审查静默失败，所有异常被 `except` 吃掉
→ 修复已应用：改用 `client.chat_json()`

### 删除只删了 1 件
```
现象：第1轮 勾选 1 个 → 删除 (1/7)
```
→ 原因：`erp_publisher.py` 的滚动使用了批量 JS `for+scrollTo`，Vue Recycle Scroller 来不及渲染中间行
→ 修复已应用：改为 Python 逐格循环 `for y in range(): page.evaluate(f"...scrollTo..."); sleep(80)`

### 命令卡住超 5 分钟
```
现象：终端无响应超过 5 分钟
```
→ 检查 Chrome 窗口是否有弹窗拦截
→ 如果被弹窗卡住，手动关弹窗后重试
→ 如果网络慢，检查 API Key 是否有效

### .env 不生效
```
现象：报 API Key 相关错误
```
→ 确认 `.env` 文件在项目根目录
→ 确认 `load_dotenv()` 能读到（可以加 `print(os.environ.get('LLM_API_KEY'))` 调试）

---

## 十、一键运行

### 首次使用（推荐跳过图片，更快）

```powershell
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "吉象星連坊（本土）" --skip-image
```

### 全量审查（含图片）

```powershell
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "吉象星連坊（本土）"
```

### 按类目自动分配（需配好映射表）

```powershell
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py
```

---

## 十一、全流程内部逻辑

```
阶段1: 合规审查
  └─ run_compliance_claim.py --review-only
      ├─ 采集箱全量扫描（跨页+虚拟滚动逐格展开）
      ├─ LLM 审查（标题，并发5线程，单次调用同时返回合规+类目）
      ├─ 不合规商品自动删除（claim-and-replace 循环法）
      └─ 过审商品留在采集箱，等待分配

阶段2: 分配 + 认领
  ├─ run_workflow.py 根据 store_category_map.json 分配类目
  └─ run_compliance_claim.py --direct-claim ID列表 --claim-to 店铺
      └─ 逐页扫描认领（单页快速通道 / 多页 claim-and-replace 循环）

阶段3: 发布
  └─ run_publish.py 店铺名 --products ID列表
      └─ claim-and-replace 循环勾选+发布，含弹窗自动处理
```

---

## 十二、验证清单

| # | 项目 | 检查方式 |
|---|------|----------|
| 1 | Python 3.12 | `& "C:\Program Files\Python312\python.exe" --version` |
| 2 | Chrome 已启动 | 有 Chrome 窗口 |
| 3 | Chrome CDP 端口 9223 | `curl -s http://127.0.0.1:9223/json/version` 有返回 |
| 4 | ERP 已登录 | 采集箱能看到「未认领」tab |
| 5 | Tesseract OCR | `python -c "import pytesseract; print('OK')"` |
| 6 | `.env` 已配置 | `Get-Content .env` 有 API Key（不要截图给 AI） |
| 7 | API Key 有效 | 第五章验证命令通过 |
| 8 | `config/config.yaml` 已确认 | 店铺名是真实名，数量对 |
| 9 | `store_category_map.json` 已配置 | 至少配置了一个店铺 |
| 10 | 依赖完整 | `& "C:\Program Files\Python312\python.exe" run_workflow.py --help` 有输出 |
