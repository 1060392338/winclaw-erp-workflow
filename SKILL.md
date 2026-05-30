---
name: cross-border-erp-automation
description: 跨境电商ERP自动化 — 采集箱审核→LLM合规+类目识别→按映射表自动分店认领→Shopee发布。纯脚本确定性执行，`run_workflow.py` 一键全流程。
---

# 跨境ERP自动化

## 触发条件

用户说「采集」「跑流程」「电商」「认领」「发布」「工作流」「审核」「审核认领」「跑一遍」「跑一下」「跑一次」「跑」时加载。配合 `SETUP_NEW_PC.md` 使用。

## 项目路径 & 环境

```
cd C:\Users\Administrator\Desktop\winclaw-erp-workflow
```
- Python 3.13.12（managed，venv at `C:\Users\Administrator\.workbuddy\binaries\python\envs\workflow\Scripts\python.exe`）
- Chrome 9223 — ERP 已登录，采集箱应有「未认领」商品
- 运行前先清状态：`Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue`
- 编码前缀：`$env:PYTHONIOENCODING='utf-8'` 或 `PYTHONIOENCODING=utf-8`
- **所有业务操作只走 `run_workflow.py`**，不直接调子脚本

---

## 🔴 会话流程决策树（新AI请逐条执行）

### 第0步：检查环境 → 告诉用户当前状态

**① 检查 Chrome**
```powershell
curl -s http://127.0.0.1:9223/json/version | head -3
```
- 成功 → "Chrome 已连接"
- 失败 → "Chrome 没连上，请确认已用 `--remote-debugging-port=9223` 启动"（参考 SETUP_NEW_PC.md 7.1）

**② 检查采集箱**
```python
from playwright.sync_api import sync_playwright
p = sync_playwright().start(); b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
for pg in b.contexts[0].pages:
    if "collect-box" in pg.url:
        has = "未认领" in pg.evaluate("document.body.innerText")
        print("UNCLAIMED_OK" if has else "NO_UNCLAIMED")
b.close(); p.stop()
```

**③ 读取可用店铺**
`store_category_map.json` 的 key 即为可用店铺列表。

**汇总告知用户：**
> Chrome ✅ | ERP 已登录 | 采集箱 N 件未认领 | 店铺：[吉象星連坊（本土）, ...]

### 第1步：询问需求

> 「采集箱 N 件未认领。怎么处理？
> A. 全部到指定店铺（告诉我店名）
> B. 按类目自动分配（需配好映射表）
> C. 先审核看看结果（--skip-image 可跳过图片审查）
> D. 直接发布草稿箱商品」

### 第2步：执行

**🔴 红线：认领前必须先问用户选哪个店铺，禁止默认选第一个店**

#### 方案A：全流程
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "用户说的店名"
```

#### 方案B：跳过图片审查（API额度不足时）
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --skip-image
```

#### 方案C：只审不发布
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --skip-publish
```

#### 方案D：直接发布草稿箱
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --all
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --products ID1,ID2
```

### 第3步：回复用户

1. 等待命令执行完成，**不要中途打断**
2. 读取 `--JSON--` 输出：pass_count / reject_count / claimed_product_ids
3. 用表格格式回复：
   - ✅ 过审 N 件（含类目和ID）
   - ❌ 拒绝 N 件（含原因）
   - 📦 无匹配类目 N 件（留在采集箱）
   - 🏪 认领到店铺：N 件
4. 如果全部被拒 → 如实告知
5. 如果有未匹配的留在采集箱 → 问用户怎么分配
6. **不要替用户做决定**

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
- 店铺名必须与 ERP 弹窗**完全一致**
- 类目见 `store_category_map.json`，可配：童裝/五金/百货/3C/服装/食品/美妆/家居/母婴/户外/宠物/其他

### 分页认领策略
- 单页（≤20件）：快速通道，一次勾选
- 多页：逐页扫描 → 第1页有匹配就认领 → 第1页无匹配就去第2页找 → 找到后翻回第1页重新勾选认领
- 认领按钮在第2+页不可用 → 自动翻回第1页重试

---

## 场景速查表

| 用户说了 | 应该怎么做 |
|----------|-----------|
| "跑一遍""审核发布" | 方案A：全流程，先问店名 |
| "跳图片" | 加 `--skip-image` |
| "先看看""先审核" | 方案C：`--skip-publish` |
| "直接发" | 方案D：`--publish --all` |
| "发这3个货号 123,456" | `--publish --products 123,456` |
| 只说了店名 | 追问：审核发布还是直接发布？ |
| 店名不确定 | 把映射表中的完整店名给用户确认 |

---

## 错误处理速查

| 现象 | 原因 | 处理 |
|------|------|------|
| Chrome 无法连接 | 没以 9223 启动 | 告诉用户用 `--remote-debugging-port=9223` |
| 未找到目标店铺 | 店名不匹配 | 检查映射表店名与ERP弹窗是否一致 |
| 无未认领商品 | 采集箱空 | 问用户是否直接发布（方案D） |
| 全部被拒 | 无合规商品 | 如实告知 |
| --skip-image 时报错 | Pydantic 校验 | 已修复：skip_image→image_compliant=True |
| page.evaluate 参数错误 | 多参数问题 | 用字典包装 `{"key1": val1, "key2": val2}` |
| 认领 count 超额 | 虚拟滚动重复计数 | 已修复为 claim-and-replace 循环 |
| 命令卡住超10分钟 | 弹窗拦截/超时 | 建议检查 Chrome 窗口，关弹窗后重试 |

---

## 完整流程（AI 不需操作）

```
① 采集箱扫描 → ② LLM审查（标题+图片） → ③ 类目识别 → ④ 不合规删除
→ ⑤ review-only 过审商品留采集箱 → ⑥ 按映射表分配
→ ⑦ direct-claim 逐页认领 → ⑧ 发布前校验 → ⑨ claim-and-replace 发布
```

**AI 只需调 `run_workflow.py`，中间所有步骤脚本自动完成。**
