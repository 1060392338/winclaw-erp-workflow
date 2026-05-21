# 新电脑部署指南 — 跨境ERP工作流

从零开始配置，到一键跑通「采集→审核→认领→发布」全流程。

---

## 一、环境准备（5分钟）

### 1.1 Python 3.12

```powershell
python --version
# 输出要 >= 3.12，如果没有去 https://www.python.org/downloads/ 下载
```

### 1.2 Chrome 浏览器（最新版）

已有则跳过，没有去 https://www.google.com/chrome/ 下载。

---

## 二、下载项目（2分钟）

```powershell
# 进工作目录
cd C:\Users\Administrator\.openclaw\workspace

# 克隆项目（或解压压缩包）
git clone https://github.com/1060392338/winclaw-erp-workflow.git cross-border-erp-agent-new
cd cross-border-erp-agent-new
```

---

## 三、安装依赖（3分钟）

```powershell
pip install -r requirements.txt
playwright install chromium
```

**如果 `pip install` 报错**，手动装：
```powershell
pip install playwright requests pyyaml python-dotenv
playwright install chromium
```

验证：
```powershell
python -c "from playwright.sync_api import sync_playwright; print('Python 依赖 OK')"
```

---

## 四、配置 API Key（必做，3分钟）

需要两种 API Key，**获取方式见下方**。

### 4.1 获取 API Key

**① DeepSeek API Key（文字模型，合规审查用）**
1. 打开 https://platform.deepseek.com/api_keys
2. 登录/注册 → 创建 API Key
3. 充值（文字模型很便宜，$5 能用很久）
4. 复制 `sk-` 开头的 key

**② 阿里百炼 DashScope API Key（图片识别用）**
1. 打开 https://bailian.console.aliyun.com
2. 登录阿里云账号 → API Key 管理 → 创建 API Key
3. 复制 `sk-` 开头的 key（DashScope 兼容模式）
4. 注意：需要开通「百炼」服务并确保有 qwen3.6-plus 模型的调用权限

### 4.2 填入 .env

把 `.env.example` 复制为 `.env` 并填入：

```powershell
cp .env.example .env
notepad .env
```

**填好的 .env 应该长这样：**

```env
# === DeepSeek 文字模型 ===
LLM_API_KEY=sk-你的DeepSeekKey           # ← 替换
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-chat
LLM_LIGHT_MODEL=deepseek-v4-flash

# === 阿里百炼 视觉模型 ===
VISION_API_KEY=sk-你的阿里百炼Key        # ← 替换
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_IMAGE_MODEL=qwen3.6-plus
```

> ⚠️ `.env` 已在 `.gitignore` 中，不会提交到 GitHub，放心填。

**验证 API Key：**
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

## 五、配置店铺（必做，2分钟）

### 5.1 修改 config/config.yaml

**把 `stores:` 下面的示例店铺换成你 ERP 账号下实际的店铺。**

怎么知道有哪些店铺？
- 登录 https://www.huohanhan.com → 认领弹窗里会列出你所有店铺
- 或者问你 ERP 管理员

```yaml
stores:
  - id: "store_1"
    name: "你的店铺名（含括号）"       # ← 改成你的店铺名，和ERP弹窗完全一致
    platform: "Shopee"
    region: "TW"
  - id: "store_2"
    name: "你的另一个店铺名"           # ← 如果你有两个店，继续加
    platform: "Shopee"
    region: "TW"
```

### 5.2 配置店铺类目映射表（强烈推荐，3分钟）

**这是自动分配模式的核心文件。** 不配的话，所有商品都不会被自动分配。

编辑 `store_category_map.json`：

```json
{
  "你的店铺名（含括号）": ["童裝", "五金"],
  "你的另一个店铺名": []
}
```

**规则说明：**
- 店铺名必须与 ERP 认领弹窗显示**完全一致**（含括号、全半角）
- 类目由 LLM 自动识别，目前支持：童裝、五金、百货、3C、服装、食品、美妆、家居、母婴、户外、宠物、其他
- 配了类目 → 该店只会收到匹配类目的商品
- 留空 `[]` → 该店不会收到任何自动分配的商品
- 不在映射表中的类目 → **合规商品**留在采集箱提示手动分配（不合规的会被直接删除）

> 💡 **如果你不确定怎么配，直接告诉 OpenClaw（我）你有几家店、分别卖什么品类，我帮你写好这个 JSON 文件。**
>
> 例：「我有两个店，A店卖童装和五金，B店卖百货」
> → 我帮你生成完整映射表。

---

## 六、启动 Chrome + 登录 ERP（必做，3分钟）

### 6.1 关闭所有 Chrome 窗口

### 6.2 以调试模式启动 Chrome

```powershell
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --remote-allow-origins=*
```

启动后 Chrome 左上角会有 "Chrome 正由自动化测试软件控制" 的提示，正常现象。

### 6.3 验证端口

```powershell
curl.exe -s http://127.0.0.1:9223/json/version
# 有 JSON 返回说明成功
```

### 6.4 登录 ERP

1. 在该 Chrome 窗口访问 https://www.huohanhan.com
2. 登录（手机号+密码+图形验证码）
3. 确认能打开采集箱：https://www.huohanhan.com/member/product/general/collect-box
4. **保持 Chrome 窗口打开，不要关闭！**

> ⚠️ ERP Session 过期是服务端行为，跨天需重新登录。

---

## 七、一键运行（1分钟）

### 方案 A：全部认领到一个店铺（推荐首次使用）

```powershell
# 清掉历史状态
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue

# 跑全流程：审核 → 认领 → 发布
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "你的店铺名"

# 如果只想审核认领不发布，加 --skip-publish
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "你的店铺名" --skip-publish
```

### 方案 B：按类目自动分配到不同店铺（需配好映射表）

```powershell
# 不传 --claim-to，自动读 store_category_map.json 分配
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py
```

### 方案 C：直接发布指定主货号

```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --products 12345,67890
```

---

## 八、验证清单

全部打勾说明配置完成：

| # | 项目 | 检查方式 | 常见问题 |
|---|------|----------|----------|
| 1 | Python 3.12 | `python --version` | 版本低 → 重装 |
| 2 | Chrome | 已打开有窗口 | 没启动 → 看 6.2 |
| 3 | Chrome 端口 | `curl.exe -s http://127.0.0.1:9223/json/version` 有返回 | 端口不通 → 检查启动参数 |
| 4 | ERP 登录 | 采集箱页面能看到「未认领」tab | 未登录 → 手动登录 |
| 5 | .env 已配 | `Get-Content .env` 有 API Key | 没配 → 看第四章 |
| 6 | API Key 有效 | 第四章验证命令通过 | 余额不足/Key无效 → 充值/重创建 |
| 7 | config.yaml 已改 | 店铺名是真实名 | 没改 → 看 5.1 |
| 8 | store_category_map.json | 已配置至少一个店铺的类目 | 没配→配一下或用方案A |
| 9 | 依赖完整 | `python run_workflow.py --help` 有输出 | 报错 → `pip install -r requirements.txt` |
| 10 | 状态文件已清 | `ls .claim_state.json` 报错（文件不存在） | 有残留 → `Remove-Item -Force .claim_state.json` |

---

## 九、常见问题

### 9.1 编码错误（乱码/UnicodeEncodeError）

```powershell
# 每次运行前加这个
$env:PYTHONIOENCODING='utf-8'
```

### 9.2 Chrome 连不上

```
ConnectionError: 无法连接到 Chrome CDP (尝试端口: 9223,9222...)
```

→ 确认 Chrome 已用 `--remote-debugging-port=9223` 启动

### 9.3 认领时说找不到店铺

```
❌ 未找到目标店铺 '你的店铺名'
```

→ 店铺名和弹窗显示不一致。检查 config.yaml 和 store_category_map.json 的店铺名是否和 ERP 弹窗完全一致（含括号、全半角）。

### 9.4 审完没有商品被认领

可能原因：
- 采集箱没有「未认领」商品
- 所有商品都被拒绝（违规内容）
- 类目匹配不到任何店铺（检查映射表）

### 9.5 发布后没看到商品

```
发布确认: 0/2 在发布中
```

→ 认领后需要等几十秒同步到发布页。代码会自动轮询最多5分钟。

---

## 十、补充：config.yaml 完整配置说明

以下是 `config/config.yaml` 各字段含义，**大多数按默认值即可**，新用户只需改 `stores:`。

| 字段 | 路径 | 必须改？ | 说明 |
|------|------|----------|------|
| `erp.url` | 货憨憨ERP地址 | ❌ 默认值即可 |
| `erp.cdp_ports` | CDP端口列表 | ❌ 默认 [9223,9222,9229,9224] |
| `stores` | **店铺列表** | **⭐ 必须改** | ERP账号绑定的所有店铺 |
| `browser.chrome_path` | Chrome路径 | ❌ 留空自动检测 |
| `browser.user_data_dir` | 用户数据目录 | ❌ 留空自动 |
| `llm.*` | LLM模型名 | ❌ .env 中配置更优先 |
| `compliance.banned_keywords` | 禁用词列表 | ❌ 内置信知识库已够用 |
| `collection.*` | 采集限制 | ❌ 默认即可 |

---

> 有问题随时找 OpenClaw（我）。配置表、映射表、分配规则都可以问我。
