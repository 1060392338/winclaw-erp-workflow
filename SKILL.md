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

---

## 🔴 会话流程决策树（新AI请逐条执行）

这是你加载后 **第一个要执行的动作**：

### 1. 确认 Chrome 在线
```powershell
curl.exe -s --connect-timeout 2 http://127.0.0.1:9223/json/version
```
失败 → 告诉用户没连上 Chrome，参考 SETUP_NEW_PC.md 第六节启动

### 2. 确认 ERP 已登录
用 Python 快速检查采集箱页面：
```python
from playwright.sync_api import sync_playwright
p = sync_playwright().start(); b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
for pg in b.contexts[0].pages:
    if "collect-box" in pg.url:
        has_unclaimed = "未认领" in pg.evaluate("document.body.innerText")
        print("UNCLAIMED_OK" if has_unclaimed else "NO_UNCLAIMED")
b.close(); p.stop()
```
- `NO_UNCLAIMED` → 告诉用户采集箱为空或未登录
- 没找到 collect-box 页面 → 告诉用户先打开采集箱

### 3. 询问用户需求（首次接触时）

**一次问清楚，不要分多次问：**

> 「采集箱 X 件未认领，已配店铺：[列出 store_category_map.json 中的店铺名]。  
> 怎么处理？选项：  
> A. 全部到指定店铺（告诉我店名）  
> B. 按类目自动分配（需映射表已配好）  
> C. 先审核看看结果再说」

**依据用户回复走对应方案：**

#### ── 方案A：用户指名店铺 ──
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店铺名"
```
- 店铺名**必须完整一致**（含括号），从 `store_category_map.json` 或从用户说的原文提取
- 产出：审核→认领→发布全流程

#### ── 方案B：用户说跑自动分配 ──
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py
```
- 自动按 `store_category_map.json` 分配
- 无匹配的商品会打印出来，**等用户回复怎么分配**
- 如果映射表未配置 → 告诉用户没配，引导用方案A或配表

#### ── 方案C：用户说先审核 ──
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --skip-publish
```
- 产出审查结果 + 认领，但**不发布**
- 用户确认后再跑发布

#### ── 特殊情况：用户给货源ID ──
```powershell
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店名" --publish --products ID1,ID2
```

### 4. 跑完后必须做的事

- **读取 `--JSON--` 输出**，解析 `pass_products` 数组，用表格格式回复用户：
  ```
  ✅ 通过：3件
    - [童裝] 主货号(637704645844) 商品名称...
    - [童裝] 主货号(758357471915) 商品名称...
  ❌ 拒绝：0件

  分配结果：
    - 店铺A ← 2件（已认领）
    - 店铺B ← 0件
    - 未匹配：1件（食品类，留在采集箱）
  ```
- **如果有未匹配的（无类目映射表）**：告诉用户商品在哪，问他怎么分配
- **不要替用户做决定**：用户没说分配方案时，不要私自认领到某个店

---

## 店铺类目映射表（store_category_map.json）

```json
{
  "你的店铺名（含括号）": ["童裝", "五金"],
  "你的另一个店铺名": []
}
```

- 店铺名必须与ERP弹窗**完全一致**
- 不在映射表中的类目 → **合规商品**留在采集箱不动（不合规的会被直接删除）
- 类目由LLM识别，从 `config/category_list.json` 读取（无需改代码）。当前支持：**童裝、五金、百货、3C、服装、食品、美妆、家居、母婴、户外、宠物、其他**。修改该 JSON 即可增减类目

**如果映射表未配或用户想补全**：
- 直接问：「你有几家店？分别卖什么品类？我帮你配好映射表」
- 用 `--add-rule` 也可以动态加

### 手动分配规则（当有无匹配商品时）

用户可以用以下格式回复分配方案：
- `全部到店铺A` → 全部去一个店
- `1到A，2到B` → 按序号分
- `食品类的到B店` → 按类目分
- `主货号(123456789)到A店` → 含ID分

**你收到回复后**：
```powershell
# 按分配结果执行对应命令
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "店铺A" --publish --products 123456789,987654321
```

---

## 常用命令速查

| 命令 | 用途 |
|------|------|
| `run_workflow.py --claim-to "店名"` | **全流程：审→认→发** |
| `run_workflow.py --claim-to "店名" --skip-publish` | 只审+认，不发 |
| `run_workflow.py --claim-to "店名" --publish --products id1,id2` | 跳过审查，直接发布指定货号 |
| `run_workflow.py` | 自动分配模式（需配映射表） |
| `run_workflow.py --add-rule "category:童裝->你的店铺名"` | 动态加分配规则 |

---

## 错误处理速查

| 报错 | 原因 | 修复 |
|------|------|------|
| `Chrome CDP 无法连接` | Chrome 没以 9223 启动 | 用户参考 SETUP 6.2 |
| `未找到目标店铺 'XXX'` | 店名不匹配 | 检查 config.yaml / 映射表中的店名 |
| `无未认领商品` | 采集箱为空 | 用户先去采集 |
| `认领成功 0 件` | 商品已被认领走或ID不存在 | 检查采集箱 |
| `stderr: UnicodeEncodeError` | 编码问题 | 代码已有 try/except 兜底 |
| `--JSON--` 没有 `pass_products` | 全部被拒或无合规商品 | 正常，告诉用户结果 |

---

## 完整流程（参考，不需逐行执行）

```
① 采集箱扫描 → ② LLM审查图片+标题 → ③ 类目识别 → ④ 按映射表分配
→ ⑤ 勾选认领 → ⑥ 轮询等待同步 → ⑦ 发布 → ⑧ 清理不合格品
```

所有子脚本的详细用法见项目内 SKILL.md 和 README.md。
