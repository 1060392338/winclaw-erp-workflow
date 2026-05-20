# 跨境ERP自动化工作流

> 采集箱审核 → LLM合规 → 货憨憨认领 → Shopee发布

## 项目目录

```
cross-border-erp-agent-new/
├── run_workflow.py              # ✅ 推荐入口 — 一键全流程脚本
├── run_compliance_claim.py      # 合规审查 + 认领到店铺
├── run_publish.py               # Shopee 批量发布（按主货号精准发布）
├── run_store_collect_flow.py    # PDD采集（DrissionPage，预留）
├── run_ext_collect.py           # PDD采集（扩展按钮）
├── workflow_deepagent.py        # ❌ 废弃（HITL不稳定，不推荐使用）
├── agent_prompts.py             # LLM角色提示词
│
├── infrastructure/
│   ├── browser.py               # Playwright CDP 连接管理
│   ├── erp_publisher.py         # ERP认领+发布操作（核心操作层）
│   ├── compliance_checker.py    # LLM合规审查
│   ├── image_checker.py         # 图片视觉检查（OCR + qwen3-vl-plus）
│   ├── taiwan_regulation.py     # 台湾广告法规审查
│   ├── title_optimizer.py       # 标题优化/繁体转换
│   ├── llm_client.py            # 统一LLM封装（文字+视觉，模型从.env读）
│   ├── config_loader.py         # 跨平台配置加载
│   ├── base_collector.py        # 采集器抽象基类
│   ├── pdd_collector.py         # DrissionPage PDD采集
│   ├── pdd_ops.py               # 反爬操作基类
│   └── pdd_network.py           # CDP网络拦截
│
├── models/
│   ├── schema.py                # 数据模型（Product, ComplianceResult）
│   └── __init__.py
│
├── .env                         # API Key 和模型配置
├── SETUP_NEW_PC.md              # 👈 新电脑部署必读
├── README.md                    # 本文件
└── 硬编码清单.md                  # 历史硬编码修复记录
```

## 🚀 快速启动

```powershell
# 1. 清空旧状态（每次跑前必做）
Remove-Item -Force .checkpoint.db, .last_thread_id, .wf_interrupt.json, .claim_state.json, .preferred_store -ErrorAction SilentlyContinue

# 2. 一键全流程：审核→删除→认领→发布到指定店铺
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

## 🔴 铁律

1. **入口固定：`run_workflow.py`**（已验证全链路稳定）。**不要用 `workflow_deepagent.py`**。
2. **每次跑前清空状态文件**：`.checkpoint.db` `.last_thread_id` `.wf_interrupt.json` `.claim_state.json` `.preferred_store`
3. **发布确认进入「发布中」即算成功**，ERP后台异步发布（约1件/分钟），不等完成。
4. **不能完全相信脚本输出** — 每步操作后必须用浏览器DOM独立验证（见下方验证章节）。
5. **用户说「跑一遍审核」= 实时拉采集箱最新数据**，禁止用 `.claim_state.json` 旧缓存回复。

## 🔧 完整流程

```
① 合规审查 → ② 认领到店铺 → ③ 发布到Shopee
```

### 阶段1：合规审查 (`run_compliance_claim.py --list-stores`)
- Playwright CDP 连接 Chrome 9223
- 读取采集箱「未认领」tab（跨页遍历+虚拟滚动全量扫描）
- LLM审查：图片视觉（qwen3-vl-plus）+ 标题合规（台湾广告法）
- ✅ 通过 → 勾选 / ❌ 拒绝 → 自动删除
- 状态文件 `.claim_state.json` 记录 pass_ids + reject_ids

### 阶段2：认领到店铺 (`run_compliance_claim.py --claim-to "店名" --resume`)
- 读取 pass_ids，跳过二次LLM审查（保证一致性）
- 勾选合规商品 → 弹出认领到店铺菜单 → 选店确认
- 认领后去草稿箱读取系统生成的主货号

### 阶段3：发布 (`run_publish.py "店名" --products 主货号列表`)
- 导航到发布页草稿箱
- 按主货号勾选商品 → 点立即发布
- 弹窗保存 → 确认「发布中」计数增加

## ✅ 操作后验证（铁律）

**每步跑完后不能只看脚本输出的 JSON/日志，必须用 Playwright 读浏览器 DOM 确认。**

### 验证发布结果
```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
import time
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url or 'shopee' in pg.url:
            pg.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=15000)
            time.sleep(3)
            text = pg.evaluate('document.body.innerText')
            import re
            draft = re.search(r'草稿箱\((\d+)\)', text)
            publishing = re.search(r'发布中\((\d+)\)', text)
            print(f'草稿箱: {draft.group(1) if draft else \"?\"}件')
            print(f'发布中: {publishing.group(1) if publishing else \"?\"}件')
            b.close(); p.stop(); exit()
print('未找到发布页')
b.close(); p.stop()
"
```

### 验证指定主货号是否在列表
```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
import time
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url or 'shopee' in pg.url:
            pg.goto('https://www.huohanhan.com/member/product/shopee/publish', wait_until='networkidle', timeout=15000)
            time.sleep(3)
            text = pg.evaluate('document.body.innerText')
            ids_to_check = ['主货号1', '主货号2']  # 替换为实际主货号
            for pid in ids_to_check:
                print(f\"{'✅' if pid in text else '❌'} {pid} {'在列表中' if pid in text else '不在列表'}\")
            b.close(); p.stop(); exit()
print('未找到发布页')
b.close(); p.stop()
"
```

## 🐛 踩过的坑（迁移必读）

| 问题 | 现象 | 原因 | 解决 |
|------|------|------|------|
| GBK中文编码崩溃 | `UnicodeEncodeError` | Windows cmd 默认 GBK | 加 `$env:PYTHONIOENCODING='utf-8'` |
| deepagent HITL EOFError | `input()` 在非交互终端报错 | 用 input() 等人输入 | 废弃 `workflow_deepagent.py`，改用 `run_workflow.py` |
| 虚拟滚动只渲染8行 | 采集箱只提取到部分商品 | vue-recycle-scroller page-mode | 脚本已内置窗口扩高+步进滚动 |
| 认领后无主货号 | 发布时找不到主货号 | 认领后需要去草稿箱读 | `run_workflow.py` 已自动完成 |
| 采集箱URL不对 | 用 `/pages/goods/crawlBox` 跳登录页 | 旧路径被302 | 正确路径 `/member/product/general/collect-box` |
| 发布页缺导航 | 脚本假设已在发布页但实际在采集箱 | 默认无导航 | 脚本已加 `page.goto()` |
| 发布页checkbox定位错 | 勾选不上商品 | checkbox不在单元格，在行级 | 改用 `[class*="virtual-table-tr"]` |
| Session过期 | 导航到ERP跳回首页 | 服务端踢session | 重新登录（图形验证码需手动输入） |
| Session检查误判 | 登录后认为是"过期" | `new_page()` 不给cookie | 复用已有tab，不创建新page |
| 模型名不兼容 | `deepseek-v4-flash` 返回空内容 | 有 `reasoning_content` | 独立脚本用 `deepseek-chat` |
| `--delete-rejected` 找不到状态文件 | pass_ids 为0时可能写入失败 | 空列表写入但读取逻辑不够健壮 | 已修复为跳过无状态文件时给友好提示 |
| LLM全部拒绝时流程结束 | 无通过商品 → 流程结束 | 正常逻辑 | 用户可以手动指定货源ID绕过审查（`--products`） |

## 📖 完成的工作流

以下流程已多次验证通过：

```
采集箱扫描 (3-5s)
  → LLM合规审查 (2-3分钟/5件)
  → 勾选合规商品 → 删除不合规商品
  → 认领到指定店铺 (30s)
  → 读取草稿箱主货号
  → 精准发布 (30s)
  → 确认进入「发布中」 ✅
```

## 环境依赖

详见 `SETUP_NEW_PC.md` — 新电脑部署指南。
