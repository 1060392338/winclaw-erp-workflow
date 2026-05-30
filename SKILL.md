---
name: cross-border-erp-automation
description: 跨境电商ERP自动化 — 采集箱审核→LLM合规+类目识别→按映射表自动分店认领→Shopee发布。纯脚本确定性执行，`run_workflow.py` 一键全流程。
---

# 跨境ERP自动化

## 触发条件

用户说「采集」「跑流程」「电商」「认领」「发布」「工作流」「审核」「审核认领」「跑一遍」「跑一下」「跑一次」「跑」「删了」「清空采集箱」时加载。配合 `SETUP_NEW_PC.md` 使用。

## 项目路径 & 环境

```
cd C:\Users\Administrator\Desktop\winclaw-erp-workflow
```

- **Python**: `C:\Program Files\Python312\python.exe`（系统 Python 3.12，所有依赖已装）
- **Chrome CDP**: 端口 9223，ERP 已登录
- **PYTHONIOENCODING**: 所有命令必须加 `$env:PYTHONIOENCODING='utf-8'`，否则 GBK 编码导致 emoji 报错
- **编码前缀固定写法**：
  ```powershell
  $env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" ...
  ```
- **清状态**：每次全流程前删 `.claim_state.json`
- **所有业务操作只走 `run_workflow.py`**，不直接调子脚本

---

## 🔴 会话流程决策树（新AI请逐条执行）

### 第0步：检查环境 → 告诉用户当前状态

**① 检查 Chrome 是否连接**
```powershell
curl -s http://127.0.0.1:9223/json/version | head -3
```
- 有 JSON 返回 → "Chrome 已连接"
- 失败 → "Chrome 没连上，请确认已用 `--remote-debugging-port=9223` 启动 Chrome"

**② 读取可用店铺**
```powershell
Get-Content store_category_map.json -Encoding UTF8
```
key 即为可用店铺列表。目前只有：吉象星連坊（本土）。

**③ 查看采集箱状态（快速 cmd）**
```powershell
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_compliance_claim.py --review-only --skip-image
```
查看输出的 "未认领: N 件" 来获取采集箱数量。

**汇总告知用户：**
> Chrome ✅ | ERP 已登录 | 采集箱 N 件未认领 | 店铺：吉象星連坊（本土）

### 第1步：询问需求

> 「采集箱 N 件未认领。怎么处理？
> A. 全流程审核→认领→发布（要店名）
> B. 只审标题不审图（--skip-image）
> C. 清空采集箱全部删除
> D. 直接发布草稿箱商品」

### 第2步：执行

**🔴 红线：认领前必须先问用户选哪个店铺，禁止默认选第一个店**

#### 方案A：全流程（含图片审查）
```powershell
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "店名"
```

#### 方案B：跳过图片审查（推荐，更快）
```powershell
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "店名" --skip-image
```

#### 方案C：清空采集箱全部删除
```powershell
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" -c "
import sys; sys.path.insert(0, '.')
from infrastructure.config_loader import ConfigLoader
from infrastructure.browser import BrowserManager
from infrastructure.erp_publisher import delete_rejected_products, scan_unclaimed_products
from config.selectors import SEL, TXT, T; import time; t = lambda ms: time.sleep(ms/1000)

bm = BrowserManager(); bm.connect(); page = bm.page
cfg = ConfigLoader().load()
page.goto(f'{cfg.erp_url}/member/product/general/collect-box', wait_until='domcontentloaded', timeout=T.NAVIGATION)
t(1000); page.wait_for_load_state('networkidle', timeout=T.NETWORK_IDLE)
page.evaluate(\"() => { document.querySelectorAll('[class*=\"dialog\"]').forEach(d => { const cb = d.querySelector('[class*=\"close\"]'); if(cb && typeof cb.click === 'function') cb.click(); }); }\")
t(500)
page.evaluate(\"(sel) => { const tabs = document.querySelectorAll(sel); for(const t of tabs) { if(t.textContent.match(/未认领|鏈棰?/)) { t.click(); return; } } }\", SEL.TAB)
page.wait_for_load_state('networkidle', timeout=T.NETWORK_IDLE); t(500)
result = scan_unclaimed_products(page)
ids = [p['erp_id'] for p in result['products'] if p.get('erp_id')]
print(f'采集箱未认领: {len(ids)} 件')
if ids: delete_rejected_products(page, ids)
print(f'✅ 删除完成')
"
```

#### 方案D：只审不发布
```powershell
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "店名" --skip-image --skip-publish
```

#### 方案E：直接发布草稿箱
```powershell
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "店名" --publish --all
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" run_workflow.py --claim-to "店名" --publish --products ID1,ID2
```

### 第3步：回复用户

1. 等待命令执行完成，**不要中途打断**
2. 读取 `--JSON--` 输出：pass_count / reject_count / claimed_product_ids
3. 用表格格式回复结果
4. 如果有未匹配的留在采集箱 → 问用户怎么处理
5. **不要替用户做决定**

---

## 已知 Bug & 修复

| Bug | 现象 | 修复 |
|-----|------|------|
| `LLMClient.chat()` 不支持 `response_format` | LLM 标题审查静默失败，所有商品全 pass | 已修复：改用 `client.chat_json()` |
| 批量 JS 滚动 (`for+scrollTo`) | Vue Recycle Scroller 不渲染中间行，商品识别不全 | 已修复：改用 Python 逐格循环 + sleep(80ms) |
| `page.evaluate()` 多参数 | `4 positional arguments but 4 were given` | 已修复：多参数用字典包装 |
| Pydantic `bool` 类型拒绝 `None` | `--skip-image` 时报 `image_compliant: Input should be a valid boolean` | 已修复：skip_image → image_compliant=True |
| `--review-only` 模式 JSON 输出缺失 | `parse_json()` 返回 None 导致流程中断 | 已修复：review-only 返回前打印 `--JSON--` 输出块 |
| GBK 编码不支持 emoji | 子进程报 `UnicodeEncodeError: 'gbk' codec` | 已修复：Popen 加 `env={"PYTHONIOENCODING": "utf-8"}` |

---

## 核心业务逻辑

### 流程
```
审查(review-only) → 分配类目 → direct-claim只认领有匹配的 → 发布
                                   ↓
                         未分配的 → 留在采集箱 ✅
```

### 三种商品处理
| 类型 | 处理 |
|------|------|
| ❌ 审查不合规 | 从采集箱删除 |
| ✅ 过审 + 有类目匹配 | 认领到店铺 → 发布 |
| ✅ 过审 + 无类目匹配 | **留在采集箱**（不删不认领）|

### 店铺映射
`store_category_map.json` → 吉象星連坊（本土）: 童裝, 五金, 家居, 其他

### 分页认领策略
- 单页（≤20件）：快速通道，一次勾选
- 多页（>20件）：逐页扫描 + claim-and-replace 循环

---

## 首次配置引导（AI 辅助新用户时用）

当用户是第一次用这个项目时，按以下流程协助：

### Step 1：展示预设类目
告诉用户系统支持哪些类目，问是否需要添加：
> "系统预设了 12 个类目：童裝/五金/百货/3C/服装/食品/美妆/家居/母婴/户外/宠物/其他。
> 每个类目都有对应的关键词和图片审查等级。你想加新的类目吗？"

### Step 2：引导用户登录 ERP 查看店铺
告诉用户先 Chrome 调试模式启动，登录 ERP，然后运行下面的命令自动读取店铺：

```powershell
$env:PYTHONIOENCODING='utf-8'; & "C:\Program Files\Python312\python.exe" -c "
import sys; sys.path.insert(0, '.')
from infrastructure.config_loader import ConfigLoader
from infrastructure.browser import BrowserManager
bm = BrowserManager(); bm.connect(); page = bm.page
cfg = ConfigLoader().load()
page.goto(f'{cfg.erp_url}/member/product/general/collect-box', wait_until='domcontentloaded', timeout=60000)
import time; time.sleep(2)
page.evaluate('() => { document.querySelectorAll(\"[class*=\"dialog\"]\").forEach(d => { const c = d.querySelector(\"[class*=\"close\"]\"); if(c && typeof c.click === \"function\") c.click(); }); }')
time.sleep(1)
page.evaluate('(sel) => { const tabs = document.querySelectorAll(sel); for(const t of tabs) { if(t.textContent.match(/未认领|鏈棰?/)) { t.click(); return; } } }', '[class*=\"t-tab\"],[class*=\"radio-button\"]')
time.sleep(2)
page.evaluate('() => { const cb = document.querySelector(\"input[type=checkbox]\"); if(cb && !cb.checked) cb.click(); }')
time.sleep(1)
page.evaluate('(t) => { const btns = document.querySelectorAll(\"button\"); for(const b of btns) { if(b.textContent.includes(t)) { b.click(); return; } } }', '认领')
time.sleep(3)
stores = page.evaluate('() => { const items = document.querySelectorAll(\"[class*=\"select-block-item\"]\"); return Array.from(items).map(el => el.textContent.trim()).filter(Boolean); }')
print(f'店铺列表:')
for i, s in enumerate(stores, 1): print(f'  {i}. {s}')
page.evaluate('() => { document.querySelectorAll(\".t-dialog__close\").forEach(c => { if(c.offsetParent !== null && typeof c.click === \"function\") c.click(); }); }')
"
```

### Step 3：让用户决定映射关系
根据读取到的店铺和预设类目，问用户：
> "你的 ERP 有 N 个店铺：...
> 系统可以识别这些类目：...
> 
> 你想怎么分配？比如：
> - 店铺 A → 接收哪些类目？
> - 店铺 B → 接收哪些类目？
> - 不在列表中的类目 → 留在采集箱"

### Step 4：更新映射表
问完后帮用户执行：
```powershell
notepad store_category_map.json
```

---

## 错误处理速查

| 现象 | 原因 | 处理 |
|------|------|------|
| Chrome 无法连接 | 没以 9223 启动 | 告诉用户用 `--remote-debugging-port=9223` 重启 Chrome |
| 未找到目标店铺 | 店名不匹配 | 检查映射表店名与 ERP 弹窗是否一致 |
| 无未认领商品 | 采集箱空 | 问用户是否直接发布草稿箱 |
| 全部被拒 | 无合规商品 | 如实告知 |
| 审查结果为 26/26 全 pass | LLM `response_format` bug | 检查是否使用 `client.chat_json()` 而非 `client.chat(response_format=...)` |
| 删除报告 1/7 实际只删 1 个 | 批量 JS 滚动导致 Vue 不渲染 | 检查 `erp_publisher.py` 的滚动循环是否用 Python 逐格 + sleep |
| 命令卡住超 5 分钟 | 弹窗拦截/网络超时 | 检查 Chrome 窗口，关弹窗后重试 |
| GBK 编码报错 | PowerShell 默认编码 | 加 `$env:PYTHONIOENCODING='utf-8'` |
