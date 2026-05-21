# 跨境ERP自动化工作流

> 采集箱审核 → LLM合规+类目识别 → 按映射表自动分店认领 → Shopee发布

## 项目目录

```
cross-border-erp-agent-new/
├── run_workflow.py              # ✅ 一键全流程入口
├── run_compliance_claim.py      # 合规审查 + 类目识别 + 认领到店铺
├── run_publish.py               # Shopee 批量发布（弹窗双路径）
├── store_category_map.json      # 店铺→类目映射表
├── assignment_rules.json        # 持久化分配规则
│
├── infrastructure/
│   ├── erp_publisher.py         # ERP核心操作（采集箱/发布页/删除）
│   ├── browser.py               # Playwright CDP 连接管理
│   ├── compliance_checker.py    # LLM合规审查
│   ├── image_checker.py         # 图片视觉检查（qwen3.6-plus）
│   ├── taiwan_regulation.py     # 台湾广告法规+政治敏感审查
│   ├── title_optimizer.py       # 标题优化
│   ├── llm_client.py            # 统一LLM封装
│   └── config_loader.py         # 配置加载
│
├── models/
│   └── schema.py                # 数据模型
├── .env                         # API Key / 模型配置
├── README.md
├── SKILL.md
└── requirements.txt
```

## 📖 新手配置

完整配置步骤见 **[SETUP_NEW_PC.md](SETUP_NEW_PC.md)**，从零开始：
1. 安装 Python 3.12 + Chrome
2. 获取 DeepSeek + 阿里百炼 API Key → 填 `.env`
3. 修改 `config/config.yaml` 中的店铺名
4. 配好 `store_category_map.json`（强烈推荐）
5. 启动 Chrome + 登录 ERP
6. 一键运行

## 🚀 一键全流程

```powershell
cd C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue

# 全部认领到指定店铺
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "順順の小屋童裝（本土）"

# 自动按类目分配（不传 --claim-to，需配好映射表）
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py
```

## 🔧 完整流程

```
① 合规审查 → ② 自动分配（按映射表） → ③ 认领 → ④ 轮询校验 → ⑤ 发布
```

### 阶段1：合规审查
- Playwright CDP 连接 Chrome 9223（三重保障导航）
- 采集箱全量扫描（跨页遍历+窗口扩高+步进滚动）
- LLM审查：图片（qwen3.6-plus）+ 标题（台湾广告法+政治敏感审查）
- ✅ 通过→勾选 / ❌ 拒绝→自动删除

### 阶段2：自动分配
- 优先级：product_rules > category_rules > store_category_map
- 匹配类目的商品自动认领发布
- 不匹配的留在采集箱并提示手动分配

### 阶段3：认领到店铺
- `--direct-claim` 直接认领指定主货号
- 认领已完成的（第一阶段）自动跳过

### 阶段4：发布前轮询校验
- 每10秒查发布页，最长等5分钟
- 只看发布中/发布成功/发布失败 tab

### 阶段5：发布
- 选店铺：完整店名精确匹配
- 按主货号勾选（支持翻页）→ 立即发布
- 弹窗双路径：未设置类目→跳过→重新保存 / 直接保存

## 当前店铺类目映射

```json
{
  "順順の小屋童裝（本土）": [
    "童裝",
    "五金"
  ],
  "吉象星連坊（本土）": [],
  "zhuangjiaen_（本土）": []
}
```

## 踩过的坑（概要）

- 店铺选择完整店名精确匹配（不用模糊匹配）
- 发布后只看发布中/发布成功/发布失败（不看草稿箱）
- `--direct-claim` 不会与第一阶段重复认领
- GBK编码：设 `$env:PYTHONIOENCODING='utf-8'`
- 虚拟滚动：窗口扩高+步进滚动全量扫描
- 导航冲突：domcontentloaded + 等待 + 重试三重保障

## 环境依赖

- **Python 3.12**
- **Chrome**（`--remote-debugging-port=9223`）
- **依赖**：`pip install playwright requests pyyaml python-dotenv Pillow`
- **模型**：.env 配置（当前 image=qwen3.6-plus, light=deepseek-v4-flash）
