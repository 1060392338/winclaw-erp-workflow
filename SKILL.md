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
2. **全流程入口：`run_workflow.py`**（已验证全链路稳定）。
3. **不询问用户**：用户说「认领到XX店」→ 直接认领，不展示列表。
4. **发布确认进入发布中即算成功**（ERP异步发布，不等完成）。
5. **用户说「跑一遍审核」= 实时拉采集箱最新数据**，禁止用 `.claim_state.json` 旧缓存回复。
6. **如果用户给货源ID → 用 `--products` 参数强制指定**，跳过审查直接认领+发布。
7. **🔴 核心铁律：不要完全相信脚本输出。每步操作后必须用浏览器DOM独立验证。**

## 前置检查

### Chrome 9223 + Session 检查

```powershell
curl.exe -s http://127.0.0.1:9223/json/version
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

### .env 配置

```env
LLM_API_KEY=sk-***
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-chat
LLM_LIGHT_MODEL=deepseek-chat
VISION_API_KEY=sk-***
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_IMAGE_MODEL=qwen3-vl-plus
```

> 模型名已从代码硬编码改为从 `.env` 读取，改配置不需要改代码。

## 🚀 一键全流程（审核→认领→发布）

```powershell
cd C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new
Remove-Item -Force .checkpoint.db, .last_thread_id, .wf_interrupt.json, .claim_state.json, .preferred_store -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "順順の小屋童裝（本土）"
```

### 子命令

| 命令 | 行为 |
|------|------|
| `--claim-to "店名"` | 完整流程：审查→删除→认领→发布（含轮询校验） |
| `--skip-publish` | 只做审查+认领，跳过发布 |
| `--publish --products id1,id2` | 直接发布指定主货号（跳过审查认领） |
| `--publish --all` | 发布草稿箱全部商品 |
| `--check-draft` | 查看草稿箱商品 |
| `--resume` | 从中断点恢复（弹窗已打开） |

### 用户指定货源ID跳过审查

```powershell
$env:PYTHONIOENCODING='utf-8'; python run_compliance_claim.py --claim-to "順順の小屋童裝（本土）" --products 货源ID1,货源ID2
$env:PYTHONIOENCODING='utf-8'; python run_publish.py "順順の小屋童裝（本土）" --products 主货号1,主货号2
```

## 工作流脚本

| 脚本 | 职责 | 角色 |
|------|------|------|
| `run_workflow.py` | **✅ 一键全流程编排（推荐入口）** | 调度台 |
| `run_compliance_claim.py` | 合规审查 + 认领到店铺 | 质检员 |
| `run_publish.py` | Shopee精准发布（按主货号）+ 弹窗双路径处理 | 发布官 |
| `run_store_collect_flow.py` | PDD采集（预留） | 搜货手 |
| `run_ext_collect.py` | 扩展采集（预留） | 搜货手 |
| `run_unified_flow.py` | 统一采集入口（预留） | 搜货手 |

## 完整流程（2026-05-20 最新版）

```
① run_compliance_claim.py --list-stores
   ├─ Playwright CDP 连 Chrome 9223（三重保障导航：domcontentloaded+networkidle+重试）
   ├─ 读取采集箱「未认领」tab（跨页遍历+窗口扩高+步进滚动全量扫描）
   ├─ LLM审查：图片（qwen3-vl-plus）+ 标题（台湾广告法）
   ├─ 通过→勾选 / 拒绝→自动删除
   └─ 输出 pass_ids + reject_ids 到 .claim_state.json

② run_compliance_claim.py --claim-to "店名" --resume
   ├─ 读取 pass_ids，跳过二次LLM审查（保证一致性）
   ├─ 勾选合规商品 → 认领到指定店铺
   ├─ 去草稿箱读取系统生成的主货号
   └─ 输出 claimed_product_ids

③ 发布前轮询校验（run_workflow.py 内置）
   ├─ 每10秒轮询发布页，search 每个主货号
   ├─ 最长等5分钟，直到全部出现才走发布
   ├─ 超时只发布已同步的商品
   └─ 不等到全部出现，绝不发布

④ run_publish.py "店名" --products 主货号列表
   ├─ 导航到发布页草稿箱
   ├─ 按主货号精准勾选
   ├─ 点击立即发布
   ├─ 弹窗双路径处理：
   │   ├─ 路径A：未设置类目 → 点跳过 → 重新点产品发布→立即发布 → 保存
   │   └─ 路径B：直接保存弹窗 → 点保存
   └─ 确认「发布中」计数增加 → 成功

⑤ 清理采集箱残留
```

## ✅ 操作后验证（铁律）

**每次执行完步骤后，必须亲自用 Playwright 读浏览器 DOM 确认。**

```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
import time; from playwright.sync_api import sync_playwright; import re
p = sync_playwright().start(); b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url or 'shopee' in pg.url:
            pg.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='domcontentloaded', timeout=15000); time.sleep(3)
            text = pg.evaluate('document.body.innerText')
            draft = re.search(r'草稿箱\((\d+)\)', text); pub = re.search(r'发布中\((\d+)\)', text)
            print(f'草稿箱: {draft.group(1) if draft else \"?\"}件 | 发布中: {pub.group(1) if pub else \"?\"}件')
            b.close(); p.stop(); exit()
print('未找到发布页'); b.close(); p.stop()
"
```

## 踩过的坑（迁移必读）

| 问题 | 现象 | 解决 |
|------|------|------|
| GBK中文编码 | `UnicodeEncodeError` | `$env:PYTHONIOENCODING='utf-8'` |
| 中文locator超时 | `text=未认领` 找不到 | 已改为JS方式，兼容编码损坏 |
| capture_output缓存 | 流程跑完才看到输出 | 已改为Popen实时输出 |
| 虚拟滚动只渲染8行 | 采集箱只提取部分商品 | 窗口扩高+步进滚动全量扫描 |
| 导航被中断 | `goto` 双重导航冲突 | 三重保障：domcontentloaded+等待+重试 |
| 采集箱URL不对 | `/pages/goods/crawlBox` 跳首页 | 用 `/member/product/general/collect-box` |
| Session过期 | 跳回登录页 | 重新登录（图形验证码需手动） |
| `deepseek-v4-flash` 空内容 | 有 `reasoning_content` | 用 `deepseek-chat` |
| 发布弹窗未设置类目 | 弹窗卡住 | 已修复：点跳过→重新点产品发布→保存 |
| 认领后发布页没有商品 | 需要等同步 | 已修复：轮询校验直到所有主货号出现 |
| 模型硬编码 | 换模型要改代码 | 已修复：从 `.env` 读取 |

## ERP 内部 URL

| 页面 | 正确路径 |
|------|----------|
| 采集箱 | `/member/product/general/collect-box` |
| 发布页 | `/member/product/shopee/publish` |
