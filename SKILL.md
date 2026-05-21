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
3. **认证领店铺：必须先展示可用店铺列表让用户选择，不能自动认领或默认店铺。**
4. **发布后确认**：发布完成后不搜索验证，直接切到发布成功或发布失败列表看商品是否存在即可。
5. **用户说「跑一遍审核」= 实时拉采集箱最新数据**，禁止用 `.claim_state.json` 旧缓存回复。
6. **如果用户给货源ID → 用 `--products` 参数强制指定**，跳过审查直接认领+发布。
7. **货源ID = 主货号**（值一样，叫法不同），发布后通过ID在发布中/发布成功/发布失败tab中确认商品状态。
8. **🔴 核心铁律：不要完全相信脚本输出。每步操作后必须用浏览器DOM独立验证（如果用户要求验证）。**

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
LLM_API_KEY=***
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-chat
LLM_LIGHT_MODEL=deepseek-chat
VISION_API_KEY=***
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_IMAGE_MODEL=qwen3-vl-plus
```

> 模型名已从代码硬编码改为从 `.env` 读取，改配置不需要改代码。

## 🚀 交互式全流程（审核→用户选店→认领→发布）

### 完整交互流程

```powershell
cd C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new
Remove-Item -Force .checkpoint.db, .last_thread_id, .wf_interrupt.json, .claim_state.json, .preferred_store -ErrorAction SilentlyContinue
```

**第一步：审核（不传 --claim-to，让用户选店铺）**
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py
```
→ 代码会自动执行 `--list-stores`，审完后打印可用店铺列表，**停下来等用户回复选哪个店**

**第二步：用户选择店铺后**
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --resume --claim-to "用户说的店名"
```
→ 认领+发布

### 子命令

| 命令 | 行为 |
|------|------|
| `--claim-to "店名"` | 完整流程：审查→删除→认领→发布 |
| `--skip-publish` | 只做审查+认领，跳过发布 |
| `--publish --products id1,id2` | 直接发布指定主货号（跳过审查认领） |
| `--publish --all` | 发布草稿箱全部商品 |
| `--check-draft` | 查看草稿箱商品 |
| `--resume` | 从中断点恢复 |

### 店铺确认规则

- **不传 `--claim-to`** → 审查后打印可用店铺列表，**停下来等用户说选哪个**，不自动决定
- 传了 `--claim-to` → 直接认领到指定店铺（当用户已明确回复店名后再传）

### 用户指定货源ID跳过审查

```powershell
$env:PYTHONIOENCODING='utf-8'; python run_compliance_claim.py --claim-to "店名" --products 货源ID1,货源ID2
$env:PYTHONIOENCODING='utf-8'; python run_publish.py "店名" --products 主货号1,主货号2
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

## 完整流程

```
① run_compliance_claim.py --list-stores
   ├─ Playwright CDP 连 Chrome 9223（三重保障导航）
   ├─ 读取采集箱「未认领」tab（跨页遍历+窗口扩高+步进滚动全量扫描）
   ├─ LLM审查：图片（qwen3-vl-plus）+ 标题（台湾广告法）
   ├─ 通过→勾选 / 拒绝→自动删除
   └─ 输出 pass_ids + reject_ids 到 .claim_state.json，打印店铺列表

② 用户选择店铺后 → run_compliance_claim.py --claim-to "店名" --resume
   ├─ 读取 pass_ids，跳过二次LLM审查
   ├─ 勾选合规商品 → 认领到用户指定店铺
   ├─ 去草稿箱读取系统生成的主货号
   └─ 输出 claimed_product_ids

③ 发布前轮询校验（run_workflow.py 内置）
   ├─ 每10秒用 --check-product 查发布页
   ├─ 最长等5分钟，直到全部出现才走发布
   ├─ --check-product 逻辑：选店铺→切发布中/发布成功/发布失败tab→读页面文本找ID
   └─ 不等到全部出现，绝不发布

④ run_publish.py "店名" --products 主货号列表
   ├─ 导航到发布页草稿箱
   ├─ 选店铺：完整店名精确匹配，取消其他店铺再选目标
   ├─ 按主货号精准勾选
   ├─ 点击立即发布
   ├─ 弹窗双路径处理：
   │   ├─ 路径A：未设置类目 → 点跳过 → 重新点产品发布→立即发布 → 保存
   │   └─ 路径B：直接保存弹窗 → 点保存
   └─ 确认发布

⑤ 发布后确认（用户要求时才做）
   └─ 选店铺标签 → 看发布成功或发布失败列表，商品在其中一个就算成功
```

## 店铺选择逻辑（关键修复）

发布页的店铺标签通过 `.t-tag--check` 选择，但该选择器会选中所有标签（地区/店铺/商户）。
**当前逻辑**：
```python
# 完整店名精确匹配，先取消其他店铺标签，再选目标
for tag in all_tags:
    if tag.text == store:
        if not checked: tag.click()
    elif '全部' not in txt and '台湾' not in txt:
        if checked: tag.click()
```

## 踩过的坑（迁移必读）

| 问题 | 现象 | 解决 |
|------|------|------|
| 店铺选择匹配不对 | `store[:4]` 模糊匹配点到「全部」 | 改完整店名精确匹配 |
| 发布只发了部分商品 | 按ID勾选没翻页 | 需确认target_ids分支有无翻页逻辑 |
| 轮询搜错字段 | 搜主货号找不到 | 改为逐tab读页面文本找ID |
| 轮询看了草稿箱 | 发布后还找草稿箱确认 | 改只看发布中/发布成功/发布失败 |
| GBK中文编码 | `UnicodeEncodeError` | `$env:PYTHONIOENCODING='utf-8'` |
| 中文locator超时 | `text=未认领` 找不到 | 已改为JS方式，兼容编码损坏 |
| capture_output缓存 | 流程跑完才看到输出 | 已改为Popen实时输出 |
| 虚拟滚动只渲染8行 | 采集箱只提取部分商品 | 窗口扩高+步进滚动全量扫描 |
| 导航被中断 | `goto` 双重导航冲突 | 三重保障：domcontentloaded+等待+重试 |
| `deepseek-v4-flash` 空内容 | 有 `reasoning_content` | 用 `deepseek-chat` |
| 发布弹窗未设置类目 | 弹窗卡住 | 已修复：点跳过→重新点产品发布→保存 |
| 认领后发布页没有商品 | 需要等同步 | 已修复：轮询校验直到所有主货号出现 |
| 模型硬编码 | 换模型要改代码 | 已修复：从 `.env` 读取 |

## ERP 内部 URL

| 页面 | 正确路径 |
|------|----------|
| 采集箱 | `/member/product/general/collect-box` |
| 发布页 | `/member/product/shopee/publish` |
