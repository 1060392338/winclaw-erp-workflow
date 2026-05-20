---
name: cross-border-erp-automation
description: 跨境电商ERP自动化 — 采集箱审核→LLM合规→货憨憨认领→Shopee发布。纯脚本确定性执行，`run_workflow.py` 一键全流程。
---

# 跨境ERP自动化

## 触发条件

用户说「采集」「跑流程」「电商」「PDD」「认领」「发布」「工作流」「审核」「审核认领」「跑一遍」时加载。

## 项目路径

⚠️ **代码在 `C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\`**

```
cd C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new
```

Python 3.12 系统环境，无虚拟环境。

## 🔴 死命令

1. **必须先清空状态文件再跑新流程**：
   ```powershell
   Remove-Item -Force .checkpoint.db, .last_thread_id, .wf_interrupt.json, .claim_state.json, .preferred_store -ErrorAction SilentlyContinue
   ```
2. **全流程入口：`run_workflow.py`**。**禁止用 `workflow_deepagent.py`**（HITL不稳定，废弃）。
3. **不询问用户**：用户说「认领到XX店」→ 直接认领，不展示列表。
4. **发布确认进入发布中即算成功**（ERP异步发布，不等完成）。
5. **用户说「跑一遍审核」= 实时拉采集箱最新数据**，禁止用 `.claim_state.json` 旧缓存回复。
6. **如果用户给货源ID → 用 `--products` 参数强制指定**，跳过审查直接认领+发布。
7. **🔴 核心铁律：不要完全相信脚本输出。每步操作后必须独立验证**，用 Playwright 直接读取浏览器 DOM 确认结果。

## 前置检查

### Chrome 9223

浏览器端口 `127.0.0.1:9223` 必须已启动（用户手动打开Chrome），不自启。

检查：
```powershell
curl.exe -s http://127.0.0.1:9223/json/version
```

ERP 采集箱和发布页可能已打开。确认 session 有效（URL未跳回登录页）。

### Session 检查

```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
from playwright.sync_api import sync_playwright
p = sync_playwright().start(); b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'collect-box' in pg.url:
            text = pg.evaluate('document.body.innerText')
            print('SESSION_OK' if '未认领' in text else 'NEED_LOGIN')
            b.close(); p.stop(); exit()
print('NEED_LOGIN'); b.close(); p.stop()
"
```

如果 NEED_LOGIN → 引导用户打开浏览器重新登录（图形验证码需手动输入）。

### 采集箱刷新

用户要求刷新时，用 Playwright CDP 连接已有 tab 执行 `goto`：
```python
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'collect-box' in pg.url:
            pg.goto('https://www.huohanhan.com/member/product/general/collect-box', wait_until='networkidle', timeout=15000)
            break
```

### .env 配置（迁移必读）

```env
LLM_API_KEY=sk-***                          # DeepSeek API Key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-chat                # 文字模型（不要用deepseek-v4-flash，有空内容问题）
LLM_LIGHT_MODEL=deepseek-chat
VISION_API_KEY=sk-***                       # 阿里百炼 DashScope API Key
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_IMAGE_MODEL=qwen3-vl-plus               # 视觉模型
```

> 模型名已从代码硬编码改为从 `.env` 读取，改配置不需要改代码。

## 🚀 一键全流程（审核→认领→发布）

```powershell
cd C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new

# 清状态
Remove-Item -Force .checkpoint.db, .last_thread_id, .wf_interrupt.json, .claim_state.json, .preferred_store -ErrorAction SilentlyContinue

# 全流程（自动识别GBK的Windows需编码前缀）
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "順順の小屋童裝（本土）"
```

### 子命令

| 命令 | 行为 |
|------|------|
| `--claim-to "店名"` | 完整流程：审查→删除→认领→发布 |
| `--skip-publish` | 只做审查+认领，跳过发布 |
| `--publish --products id1,id2` | 直接发布指定主货号（跳过审查认领） |
| `--publish --all` | 发布草稿箱全部商品 |
| `--check-draft` | 查看草稿箱商品 |
| `--resume` | 从中断点恢复（弹窗已打开） |

### 用户指定货源ID跳过审查

```powershell
$env:PYTHONIOENCODING='utf-8'; python run_compliance_claim.py --claim-to "順順の小屋童裝（本土）" --products 690290427565,520975599373

$env:PYTHONIOENCODING='utf-8'; python run_publish.py "順順の小屋童裝（本土）" --products 690290427565,520975599373
```

## 工作流脚本

| 脚本 | 职责 | 角色 |
|------|------|------|
| `run_workflow.py` | **✅ 一键全流程编排（推荐入口）** | 调度台 |
| `run_compliance_claim.py` | 合规审查 + 认领到店铺 | 质检员 |
| `run_publish.py` | Shopee精准发布（按主货号） | 发布官 |
| `workflow_deepagent.py` | ❌ 废弃（HITL不稳定） | — |
| `run_store_collect_flow.py` | PDD采集 | 搜货手（预留） |

## 完整流程说明

```
① run_compliance_claim.py --list-stores
   ├─ Playwright CDP 连 Chrome 9223
   ├─ 读取采集箱「未认领」tab（跨页遍历+虚拟滚动全量扫描）
   ├─ LLM审查：图片（qwen3-vl-plus）+ 标题（台湾广告法）
   ├─ 通过→勾选 / 拒绝→自动删除
   └─ 输出 pass_ids + reject_ids 到 .claim_state.json

② run_compliance_claim.py --claim-to "店名" --resume
   ├─ 读取 pass_ids，跳过二次LLM审查（保证一致性）
   ├─ 勾选合规商品 → 认领到指定店铺
   ├─ 去草稿箱读取系统生成的主货号
   └─ 输出 claimed_product_ids

③ run_publish.py "店名" --products 主货号列表
   ├─ 导航到发布页草稿箱
   ├─ 按主货号勾选商品
   ├─ 点击立即发布 → 弹窗保存
   └─ 确认「发布中」计数增加 → 成功
```

## ✅ 操作后验证（铁律）

**每次执行完步骤后，必须亲自用 Playwright 读浏览器 DOM 确认。**

### 验证发布结果
```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
import time; from playwright.sync_api import sync_playwright
p = sync_playwright().start(); b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url or 'shopee' in pg.url:
            pg.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=15000); time.sleep(3)
            text = pg.evaluate('document.body.innerText'); import re
            draft = re.search(r'草稿箱\((\d+)\)', text); pub = re.search(r'发布中\((\d+)\)', text)
            print(f'草稿箱: {draft.group(1) if draft else \"?\"}件 | 发布中: {pub.group(1) if pub else \"?\"}件')
            b.close(); p.stop(); exit()
print('未找到发布页'); b.close(); p.stop()
"
```

### 验证指定主货号是否在草稿箱
```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
import time; from playwright.sync_api import sync_playwright
p = sync_playwright().start(); b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url:
            pg.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=15000); time.sleep(3)
            text = pg.evaluate('document.body.innerText')
            for pid in ['主货号1', '主货号2']:
                print(f\"{'✅' if pid in text else '❌'} {pid} {'在列表中' if pid in text else '不在列表'}\")
            b.close(); p.stop(); exit()
print('未找到发布页'); b.close(); p.stop()
"
```

## 已知问题

| 问题 | 对策 |
|------|------|
| LLM审查全部拒绝 | 告诉用户结果，用户可指定货源ID强制处理（`--products`）或采集新商品 |
| GBK中文编码 | 设置 `$env:PYTHONIOENCODING='utf-8'` |
| 采集箱虚拟滚动只渲染首屏 | 脚本已内置窗口扩高+步进滚动全量提取 |
| 发布异步（~1件/分钟） | 确认进入发布中即算成功，不等完成 |
| OCR不可用（pytesseract未安装） | LLM视觉模型替代，不影响功能 |
| deepagent HITL 不稳定 | 废弃，改用 `run_workflow.py` |
| 模型硬编码 | 已修复为从 `.env` 读取，改 .env 即可换模型 |
| `workflow_deepagent.py` 旧入口被调 | 告诉用户：请改用 `run_workflow.py` |

## ERP 内部 URL

| 页面 | 正确路径 |
|------|----------|
| 采集箱 | `/member/product/general/collect-box` |
| 发布页 | `/member/product/shopee/publish` |

> 不要用 `/pages/goods/crawlBox` — 会被302到首页。
