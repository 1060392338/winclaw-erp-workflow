# 跨境ERP自动化工作流

> 采集箱审核 → LLM合规 → 货憨憨认领 → Shopee发布

## 项目目录

```
cross-border-erp-agent-new/
├── run_workflow.py              # ✅ 一键全流程入口
├── run_compliance_claim.py      # 合规审查 + 认领到店铺
├── run_publish.py               # Shopee 批量发布（弹窗双路径处理）
├── run_store_collect_flow.py    # PDD采集（预留）
├── run_ext_collect.py           # 扩展采集（预留）
├── run_unified_flow.py          # 统一采集入口（预留）
├── agent_prompts.py             # LLM角色提示词
│
├── infrastructure/
│   ├── erp_publisher.py         # ERP核心操作（采集箱/发布页/删除）
│   ├── browser.py               # Playwright CDP 连接管理
│   ├── compliance_checker.py    # LLM合规审查
│   ├── image_checker.py         # 图片视觉检查（qwen3-vl-plus）
│   ├── taiwan_regulation.py     # 台湾广告法规审查
│   ├── title_optimizer.py       # 标题优化/繁体转换
│   ├── llm_client.py            # 统一LLM封装（模型从.env读）
│   ├── config_loader.py         # 配置加载
│   └── ...                      # 采集相关（预留）
│
├── models/
├── .env                         # API Key
├── SETUP_NEW_PC.md              # 部署指南
├── README.md                    # 本文件
├── SKILL.md                     # OpenClaw Skill
├── requirements.txt
└── AI驱动工作流开发教程.md       # 教程
```

## 🚀 快速启动

```powershell
Remove-Item -Force .checkpoint.db, .last_thread_id, .wf_interrupt.json, .claim_state.json, .preferred_store -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "順順の小屋童裝（本土）"
```

## 🔴 铁律

1. **入口：`run_workflow.py`**
2. **每次跑前清空状态文件**
3. **发布进入「发布中」即算成功**（异步，不等完成）
4. **不能完全相信脚本输出** — 每步用浏览器DOM验证
5. **不询问用户** — 指定了店直接认领

## 🔧 完整流程（5步）

```
① 合规审查 → ② 认领到店铺 → ③ 轮询校验 → ④ 发布 → ⑤ 清理残留
```

### 阶段1：合规审查
- Playwright CDP 连接 Chrome 9223（三重保障：domcontentloaded+等待+重试）
- 采集箱全量扫描（跨页遍历+窗口扩高+步进滚动）
- LLM审查：图片（qwen3-vl-plus）+ 标题（台湾广告法）
- ✅ 通过→勾选 / ❌ 拒绝→自动删除

### 阶段2：认领到店铺
- 读取 pass_ids，跳过二次LLM审查
- 勾选 → 认领到指定店铺 → 读取主货号

### 阶段3：发布前轮询校验
- 每10秒用 `--check-product` 查发布页
- 最长等5分钟，所有主货号出现才走发布
- 超时只发已同步的

### 阶段4：发布
- 按主货号精准勾选 → 立即发布
- 弹窗双路径：
  - **路径A**：未设置类目 → 点跳过 → 重新点产品发布→立即发布 → 保存
  - **路径B**：直接保存弹窗 → 点保存

### 阶段5：清理残留

## 验证

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
"
```

## 踩过的坑

| 问题 | 现象 | 解决 |
|------|------|------|
| GBK编码 | `UnicodeEncodeError` | 加编码前缀 |
| 中文定位失败 | `text=未认领` 找不到 | 改为JS方式兼容编码损坏 |
| 输出看不到 | 跑到尾才出日志 | 改为Popen实时输出 |
| 导航冲突 | `goto` 被中断 | 三重保障+重试 |
| 虚拟滚动漏数据 | 只提取8行 | 窗口扩高+步进滚动 |
| 模型空内容 | `deepseek-v4-flash` 没输出 | 用 `deepseek-chat` |
| 发布弹窗卡住 | 未设置类目 | 双路径处理 |
| 同步延迟 | 认领后发布页没商品 | 轮询校验直到出现 |

## 环境依赖

详见 `SETUP_NEW_PC.md`。
