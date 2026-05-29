---
name: cross-border-erp-automation
description: 跨境电商ERP自动化 — 采集箱审核→LLM合规+类目识别→按映射表自动分店认领→Shopee发布。纯脚本确定性执行，`run_workflow.py` 一键全流程。
---

# 跨境ERP自动化

## 触发条件

用户说「采集」「跑流程」「电商」「PDD」「认领」「发布」「工作流」「审核」「审核认领」「跑一遍」「跑一下」「跑一次」「跑」时加载。

## 项目路径 & 环境

```
cd C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new
```
- Python 3.12 系统环境，无虚拟环境
- Chrome 9223 ─ERP 已登录，采集箱有「未认领」商品
- 运行前先清状态：`Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue`
- 编码前缀：`$env:PYTHONIOENCODING='utf-8'`
- **所有业务操作只走 `run_workflow.py`**，不直接调子脚本

---

## 🔴 会话流程决策树（新AI请逐条执行）

### 第0步：检查环境 → 告诉用户当前状态

检查完成后**必须把结果告诉用户**，不能默默往下走：

**① 检查 Chrome**
```powershell
curl.exe -s --connect-timeout 2 http://127.0.0.1:9223/json/version
```
- 成功 → 告诉用户 "Chrome 已连接"
- 失败 → "Chrome 没连上，请确认已用 `--remote-debugging-port=9223` 参数启动 Chrome"（参考 SETUP_NEW_PC.md 6.2）

**② 检查 ERP 登录 + 采集箱是否有未认领商品**
```python
from playwright.sync_api import sync_playwright
p = sync_playwright().start(); b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
for pg in b.contexts[0].pages:
    if "collect-box" in pg.url:
        has_unclaimed = "未认领" in pg.evaluate("document.body.innerText")
        print("UNCLAIMED_OK" if has_unclaimed else "NO_UNCLAIMED")
b.close(); p.stop()
```
- `UNCLAIMED_OK` → "ERP 已登录，采集箱有未认领商品"
- `NO_UNCLAIMED` → "采集箱为空或已全部认领过了"
- 没找到 collect-box 页面 → "请先打开采集箱页面（https://www.huohanhan.com/member/product/general/collect-box）"

**③ 检查有哪几个店铺**
读取 `store_category_map.json` 的 key 作为可用店铺列表。

**检查完成后，汇总告知用户：**
> Chrome ✅ | ERP 已登录 | 采集箱 N 件未认领 | 已配店铺：[店A, 店B]

### 第1步：询问需求

**一次问清楚，不要分多次问：**

> 「采集箱 N 件未认领，已配店铺：[列出 store_category_map.json 中的店铺名]。  
> 怎么处理？选项：  
> A. 全部到指定店铺（告诉我店名）  
> B. 按类目自动分配（需映射表已配好）  
> C. 先审核看看结果再说（认领但不发布）  
> D. 直接发布草稿箱的现有商品（跳过审核认领）」

### 第2步：按用户选择执行

**🔴🔴🔴 红线（认领前）**
- 必须先问用户选哪个店铺，**拿到明确答复后才能执行 `--claim-to`**
- 禁止从 `store_category_map.json` 拿第一个店名就跑了
- 用户没说店名时追问，不要自己猜
- 用户说了店名 → 原文提取（含括号、全半角保持一致）传给 `--claim-to`

#### 方案A：全流程（审核→认领→发布到指定店铺）
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "用户说的店名"
```
- 产出：审核→认领→发布全流程
- 发布阶段**代码会自动**切到该店铺筛选草稿再发，AI 不需额外操作

#### 方案B：按类目自动分配
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py
```
- 自动按 `store_category_map.json` 分配
- 无匹配的商品会打印出来 → **等用户回复怎么分配**
- 如果映射表未配 → 告诉用户没配，引导用方案A或找用户配表

#### 方案C：先审核认领，不发布
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --skip-publish
```
- 只审+认，不发
- 用户确认后再跑发布：
  ```powershell
  $env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --all
  ```

#### 方案D：直接发布（跳过审核认领，只发草稿箱现有商品）
```powershell
# 发布某店铺全部草稿
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --all

# 只发指定主货号
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --products 12345,67890
```
- **适用于**：用户已经手动认领好了、或者想重新发布之前认领过的商品
- **不经过** 采集箱扫描/合规审查/认领，直接到发布页

#### 特殊情况：用户给货源ID
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --products ID1,ID2
```

### 第3步：跑完后回复用户

**必须做的事（逐条）：**

1. **等待命令执行完成** — `run_workflow.py` 全流程包含认领后轮询等待同步（最长5分钟），不要中途打断，等它跑完
2. **读取 `--JSON--` 输出**，解析各字段：
   - `pass_count` — 通过审查的商品数
   - `reject_count` — 被拒绝的商品数
   - `pass_products` — 通过商品数组（含 id / title / category / status）
   - `claimed_product_ids` — 实际认领成功的商品ID列表
3. **用表格格式回复用户**：
   ```
   ✅ 审核通过：3件
     - [童裝] 主货号(637704645844) 商品名称...
     - [五金] 主货号(758357471915) 商品名称...
   ❌ 拒绝：0件
   
   认领到店铺：店铺A（3件）
   发布结果：3件已提交发布
   ```
4. **如果全部被拒（`--JSON--` 无 pass_products）** → 如实告诉用户，不用再问分配
5. **如果有未匹配的商品留在采集箱**（类目不在映射表中）→ 告诉用户，问怎么处理
6. **不要替用户做决定** — 用户没说分配方案时，不要私自分

---

## 场景速查表（新AI快速判断）

| 用户说了 | 应该怎么做 |
|----------|-----------|
| "跑一遍""审核发布" | 方案A：全流程，问店名或自动分配 |
| "先看看""先审核" | 方案C：`--skip-publish` |
| "直接发""发一下草稿" | 方案D：`--publish --all` |
| "发这3个货号 123,456" | 特殊情况：`--publish --products 123,456` |
| "帮我采集XX店的东西" | 告知采集模块暂未接入（预留），引导先审采集箱现有商品 |
| 只说了店名没说要做什么 | 追问用途：审核发布？还是直接发布？ |
| 店名不确定/括号有差异 | 把映射表中的完整店名发给用户确认，不要自己替换 |

---

## 店铺类目映射表（store_category_map.json）

```json
{
  "你的店铺名（含括号）": ["童裝", "五金"],
  "你的另一个店铺名": []
}
```

- 店铺名必须与ERP弹窗**完全一致**
- **留空 `[]` → 该店被排除在自动分配之外，不会收到任何商品**
- **完全没出现在映射表中的店铺 → 等同于未配置，也不会收到自动分配**
- 不在映射表中的类目 → **合规商品**留在采集箱不动（不合规的会被直接删除）
- 类目由LLM识别，从 `config/category_list.json` 读取（无需改代码）。当前支持的类目：**童裝、五金、百货、3C、服装、食品、美妆、家居、母婴、户外、宠物、其他**。修改该 JSON 即可增减

**如果映射表未配或用户想补全**：
- 直接问：「你有几家店？分别卖什么品类？我帮你配好」
- 用 `--add-rule` 也可以动态加规则

### 手动分配规则（当有无匹配商品时）

用户回复格式：
- `全部到店铺A` → 全部一个店
- `1到A，2到B` → 按序号分
- `食品类的到B店` → 按类目分
- `主货号(123456789)到A店` → 含ID分

**你收到回复后**：
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店铺A" --publish --products 123456789,987654321
```

---

## 常用命令速查

| 命令 | 用途 | 对应方案 |
|------|------|----------|
| `run_workflow.py --claim-to "店名"` | **全流程：审→认→发** | A |
| `run_workflow.py --claim-to "店名" --skip-publish` | 只审+认，不发 | C |
| `run_workflow.py --claim-to "店名" --publish --all` | 直接发布全部草稿 | D |
| `run_workflow.py --claim-to "店名" --publish --products id1,id2` | 直接发布指定货号 | 特殊情况 |
| `run_workflow.py` | 按映射表自动分配 | B |
| `run_workflow.py --add-rule "category:童裝->店名"` | 动态加分配规则 | — |

---

## 错误处理速查（含 AI 应对）

| 现象 | 原因 | AI 应该怎么做 |
|------|------|--------------|
| 命令返回 `Chrome CDP 无法连接` | Chrome 没以 9223 启动 | 告诉用户：用 `--remote-debugging-port=9223` 启动 Chrome，参考 SETUP 6.2 |
| 命令返回 `未找到目标店铺 'XXX'` | 店名不匹配 | 告诉用户：检查 config.yaml / 映射表中的店名和 ERP 弹窗是否完全一致 |
| 命令返回 `无未认领商品` | 采集箱为空或已全部认领 | 如实告诉用户，问是否需要直接发布（方案D） |
| 命令返回 `认领成功 0 件` | 商品已被认领走或ID不存在 | 建议用户检查采集箱确认 |
| `--JSON--` 没有 `pass_products` | 全部被拒或无合规商品 | 告诉用户本次审核结果，无需再操作 |
| 命令卡住超过10分钟没输出 | 可能超时/Chrome 弹窗拦截 | 告诉用户目前卡住，建议检查 Chrome 窗口是否有弹窗未关，然后重试 |
| 用户说"发错了/发多了" | 商品已提交发布 | 告知发出去的无法撤回，下次注意；推荐先 `--skip-publish` 预览结果 |

---

## 完整流程（内部逻辑，AI 不需要操作）

```
① 采集箱扫描 → ② LLM审查图片+标题 → ③ 类目识别 → ④ 按映射表分配
→ ⑤ 勾选认领 → ⑥ 轮询等待同步（最长5分钟） → ⑦ 店名筛选发鬼页 → ⑧ 发布
→ ⑨ 清理不合格品
```

**AI 只需调 `run_workflow.py`，中间所有步骤脚本自动完成。**
