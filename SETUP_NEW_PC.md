# 新电脑部署指南 — 跨境ERP工作流

## 一、环境要求

- **OS**: Windows 10/11
- **Python**: 3.12（`python --version`）
- **Chrome**: 最新版

## 二、项目代码

```powershell
cd C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new
```

## 三、Python 依赖

```powershell
pip install playwright requests pyyaml python-dotenv Pillow
playwright install chromium
```

验证：
```powershell
python -c "from playwright.sync_api import sync_playwright; print('OK')"
```

## 四、API Key 配置

把 `.env.example` 复制为 `.env` 并填入：

```env
LLM_API_KEY=sk-***                    # DeepSeek
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-chat
LLM_LIGHT_MODEL=deepseek-v4-flash
VISION_API_KEY=sk-***                  # 阿里百炼 DashScope
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_IMAGE_MODEL=qwen3.6-plus
```

验证：
```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
from openai import OpenAI; import os; from dotenv import load_dotenv; from pathlib import Path
load_dotenv()
c = OpenAI(api_key=os.environ.get('LLM_API_KEY',''), base_url=os.environ.get('LLM_BASE_URL',''))
r = c.chat.completions.create(model='deepseek-chat', messages=[{'role':'user','content':'hi'}], max_tokens=10)
print('文字模型OK:', r.choices[0].message.content)
"
```

## 五、启动 Chrome

```powershell
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --remote-allow-origins=*
```

验证：
```powershell
curl.exe -s http://127.0.0.1:9223/json/version
```

## 六、登录 ERP

1. 打开的Chrome中访问 `https://www.huohanhan.com`
2. 登录（手机号+密码+图形验证码）
3. 确认采集箱：`/member/product/general/collect-box`
4. **保持浏览器不关闭**

Session 过期是服务端行为，跨天需重新登录。

## 七、配置店铺类目映射表（强烈推荐）

自动分配模式（不传 `--claim-to` 时）依赖 `store_category_map.json` 决定商品去哪个店。
**如果不配这个文件，所有商品都不会被分配，流程会停在采集箱让你手动分配。**

```json
{
  "順順の小屋童裝（本土）": ["童裝", "五金"],
  "吉象星連坊（本土）": [],
  "zhuangjiaen_（本土）": []
}
```

- 店铺名必须与ERP弹窗显示完全一致（含括号）
- 类目由LLM自动识别（童裝/五金/百货/3C/服装/食品/美妆/家居/母婴/户外/宠物/其他）
- 不在映射表中的类目 → 留在采集箱，提示手动分配

💡 **如果你懒得自己配这个 JSON，可以直接找 OpenClaw（我）帮你配置。告诉我有几家店、分别卖什么品类就行。**

> 也可用 `--add-rule` 动态添加类目分配规则：
> ```
> python run_workflow.py --add-rule "category:童裝->順順の小屋童裝（本土）"
> ```

## 八、运行工作流

```powershell
# 清状态 + 跑全流程
Remove-Item -Force .claim_state.json -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "順順の小屋童裝（本土）"

# 自动分配模式（不传 --claim-to，需配好映射表）
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py
```

## 九、验证清单

| 项目 | 检查方式 |
|------|----------|
| Python 3.12 | `python --version` |
| Chrome 9223 | `curl.exe -s http://127.0.0.1:9223/json/version` |
| ERP 登录 | 采集箱看到商品 |
| .env 存在 | `Get-Content .env` |
| store_category_map.json 已配 | `Get-Content store_category_map.json` |
| 依赖完整 | `python run_compliance_claim.py --help` |
