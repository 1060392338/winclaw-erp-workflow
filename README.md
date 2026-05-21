# 跨境ERP自动化工作流

> 采集箱审核 → LLM合规 → 用户选店 → 货憨憨认领 → Shopee发布

## 项目目录

```
cross-border-erp-agent-new/
├── run_workflow.py              # ✅ 一键全流程入口
├── run_compliance_claim.py      # 合规审查 + 认领到店铺
├── run_publish.py               # Shopee 批量发布（弹窗双路径处理）
│
├── infrastructure/
│   ├── erp_publisher.py         # ERP核心操作（采集箱/发布页/删除）
│   ├── browser.py               # Playwright CDP 连接管理
│   ├── compliance_checker.py    # LLM合规审查
│   ├── image_checker.py         # 图片视觉检查（qwen3-vl-plus）
│   ├── taiwan_regulation.py     # 台湾广告法规审查
│   ├── title_optimizer.py       # 标题优化/繁体转换
│   ├── llm_client.py            # 统一LLM封装（模型从.env读）
│   └── config_loader.py         # 配置加载
│
├── models/
├── .env                         # API Key
├── README.md                    # 本文件
├── SKILL.md                     # OpenClaw Skill
└── requirements.txt
```

## 🚀 交互式流程

```powershell
# 1. 清空状态
Remove-Item -Force .checkpoint.db, .last_thread_id, .wf_interrupt.json, .claim_state.json, .preferred_store -ErrorAction SilentlyContinue

# 2. 先审核（不指定店铺，等用户选）
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py

# 3. 用户回复选店后，再接续认领+发布
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --resume --claim-to "用户选的店名"
```

## 🔴 铁律

1. **入口：`run_workflow.py`**
2. **每次跑前清空状态文件**
3. **必须先展示可用店铺列表让用户选择，不能自动认领**
4. **发布后不搜索验证，直接看发布成功或发布失败列表即可**
5. **不能完全相信脚本输出** — 用户要求时才做DOM验证
6. **货源ID = 主货号**（值一样，叫法不同）

## 🔧 完整流程

```
① 合规审查 → ② 用户选店 → ③ 认领 → ④ 轮询校验 → ⑤ 发布 → ⑥ 确认
```

### 阶段1：合规审查
- Playwright CDP 连接 Chrome 9223（三重保障）
- 采集箱全量扫描（跨页遍历+窗口扩高+步进滚动）
- LLM审查：图片（qwen3-vl-plus）+ 标题（台湾广告法）
- ✅ 通过→勾选 / ❌ 拒绝→自动删除
- 打印可用店铺列表，等用户选择

### 阶段2：用户选择店铺
用户回复后，传 `--claim-to "店名" --resume` 继续

### 阶段3：认领到店铺
- 读取 pass_ids，跳过二次LLM审查
- 勾选 → 认领到用户指定店铺 → 读取主货号

### 阶段4：发布前轮询校验
- 每10秒用 `--check-product` 查发布页
- 逻辑：选店铺 → 切发布中/发布成功/发布失败 tab → 读页面文本找ID
- 最长等5分钟，全部出现才走发布

### 阶段5：发布
- 选店铺：完整店名精确匹配
- 按主货号勾选 → 立即发布
- 弹窗双路径：
  - **路径A**：未设置类目 → 点跳过 → 重新点产品发布→立即发布 → 保存
  - **路径B**：直接保存弹窗 → 点保存

### 阶段6：发布后确认
- 切到发布成功或发布失败列表
- 商品在其中一个就算成功

## 店铺选择逻辑

发布页店铺标签通过 `.t-tag--check` 选中（含地区/店铺/商户所有标签）。
改为**完整店名精确匹配**，先取消其他店铺再选目标，避免点到「全部」。
```python
# 伪代码
for tag in all_tags:
    if tag.text == store: tag.click()  # 选目标
    elif tag是其他店铺名且已选中: tag.click()  # 取消
```

## 踩过的坑

| 问题 | 现象 | 解决 |
|------|------|------|
| 店铺选择匹配不对 | `store[:4]` 点到「全部」 | 完整店名精确匹配 |
| 轮询搜错字段 | 主货号搜不到 | 改为逐tab读页面文本 |
| 轮询看了草稿箱 | 发布后还查草稿箱 | 改只看发布中/成功/失败 |
| GBK编码 | `UnicodeEncodeError` | 加编码前缀 |
| 中文定位失败 | `text=未认领` 找不到 | 改为JS方式 |
| 虚拟滚动漏数据 | 只提取8行 | 窗口扩高+步进滚动 |
| 模型空内容 | `deepseek-v4-flash` 没输出 | 用 `deepseek-chat` |
| 发布弹窗卡住 | 未设置类目 | 双路径处理 |
| 同步延迟 | 认领后发布页没商品 | 轮询校验直到出现 |

## 环境依赖

- **Python 3.12**
- **Chrome**（需启动 `--remote-debugging-port=9223`）
- **依赖**：`pip install playwright requests pyyaml python-dotenv Pillow langgraph langchain-openai openai`
