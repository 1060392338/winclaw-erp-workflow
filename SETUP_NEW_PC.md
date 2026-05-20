# 新电脑部署指南 — 跨境ERP工作流

**目标：一次配置，每次跑通**

## 一、环境要求

- **OS**: Windows 10/11
- **Python**: 3.12（确认 `python --version`）
- **Chrome**: 最新版（用于CDP调试连接）
- **浏览器窗口**: 保持打开（工作流通过CDP连已有Chrome，不自启）

## 二、项目代码

把 `cross-border-erp-agent-new/` 整个目录复制到新电脑任意位置。

```powershell
# 建议放到工作区
C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\
```

## 三、Python 依赖

```powershell
pip install playwright requests pyyaml python-dotenv Pillow
pip install langgraph langchain-openai langgraph-checkpoint-sqlite openai
playwright install chromium
```

> 不需要虚拟环境，系统Python即可。

验证：
```powershell
python -c "from playwright.sync_api import sync_playwright; from langchain_openai import ChatOpenAI; print('依赖OK')"
```

## 四、API Key 配置 ⚠️ 最关键一步

把对应的 `.env` 文件复制到项目目录下。配置内容：

```
# === 文字模型（DeepSeek） ===
LLM_API_KEY=sk-你的deepseek_key
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_TEXT_MODEL=deepseek-chat
LLM_LIGHT_MODEL=deepseek-chat

# === 视觉模型（阿里百炼DashScope） ===
VISION_API_KEY=sk-你的dashscope_key
VISION_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_IMAGE_MODEL=qwen3-vl-plus
```

### 获取API Key

| 用途 | 渠道 | 地址 |
|------|------|------|
| DeepSeek 文字模型 | deepseek.com | 控制台 → API Keys |
| DashScope 视觉模型 | 阿里云百炼 | 控制台 → API Key管理 |

### 验证配置
```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
from openai import OpenAI; import os; from dotenv import load_dotenv; from pathlib import Path
load_dotenv(Path(r'项目目录') / '.env')
c = OpenAI(api_key=os.environ.get('LLM_API_KEY',''), base_url=os.environ.get('LLM_BASE_URL',''))
r = c.chat.completions.create(model='deepseek-chat', messages=[{'role':'user','content':'hi'}], max_tokens=10)
print('文字模型OK:', r.choices[0].message.content)
"
```

## 五、启动 Chrome（调试模式）

**关闭所有已打开的 Chrome 窗口后**运行：

```powershell
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9223 --remote-allow-origins=*
```

验证：
```powershell
curl.exe -s http://127.0.0.1:9223/json/version
# 返回 JSON 说明成功
```

> 注意：每次重启Chrome都要用这个命令行。直接双击Chrome图标不会开启调试端口。

## 六、登录货憨憨 ERP

1. 在已启动的 Chrome 中访问 `https://www.huohanhan.com`
2. 点「登录」→ 输入手机号+密码
3. **手动输入图形验证码**（无法自动识别，必须用人眼）
4. 登录后访问采集箱确认：`/member/product/general/collect-box`
5. **保持浏览器不关闭** — 关闭后需要重新登录

### Session 过期

Session 过期是 ERP 服务端行为，非本地问题。常见情况：
- 跨天空闲 → 自动过期
- 切换标签页后 → 可能有缓存但API调用返回401
- Chrome重启 → 必须重新登录

**解决方法：重新登录（步骤3-4）。**

### 判断 Session 是否有效

```powershell
$env:PYTHONIOENCODING='utf-8'; python -c "
from playwright.sync_api import sync_playwright; import time
p = sync_playwright().start(); b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'collect-box' in pg.url:
            text = pg.evaluate('document.body.innerText')
            if '未认领' in text and '登录' not in text.split('首页')[0]:
                print('SESSION_OK')
            else:
                print('NEED_LOGIN')
            b.close(); p.stop(); exit()
print('NEED_LOGIN (未找到采集箱tab)')
b.close(); p.stop()
"
```

## 七、运行工作流（首次验证）

```powershell
cd 项目目录

# 清空旧状态
Remove-Item -Force .checkpoint.db, .last_thread_id, .wf_interrupt.json, .claim_state.json, .preferred_store -ErrorAction SilentlyContinue

# 全流程：审核→删除→认领→发布
$env:PYTHONIOENCODING='utf-8'; python run_workflow.py --claim-to "順順の小屋童裝（本土）"
```

预期输出：
```
阶段1/3: 合规审查 → 删除不合规商品
  ...
  通过: N 件 / 拒绝: M 件

阶段2/3: 自动认领到 → 順順の小屋童裝（本土）
  ...
  ✅ 认领完成! 主货号: 4件

阶段3/3: 发布到 Shopee
  ...
  ✅ 发布完成!
```

## 八、OpenClaw Skill 注册（如果是新 OpenClaw 环境）

把 `~/.openclaw/skills/跨境erp工作流/SKILL.md` 复制到新电脑的同路径下。

```powershell
# 创建目录
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.openclaw\skills\跨境erp工作流"
# 复制文件（从项目目录）
Copy-Item .\SKILL.md "$env:USERPROFILE\.openclaw\skills\跨境erp工作流\SKILL.md"
```

## 九、常见问题

### 1. GBK 中文编码错误

```
UnicodeEncodeError: 'gbk' codec can't encode character
```

✅ 在所有运行命令前加 `$env:PYTHONIOENCODING='utf-8';`

### 2. Chrome 连接失败

```
❌ 连接失败: connect ECONNREFUSED 127.0.0.1:9223
```

✅ 确认 Chrome 是否以调试模式启动（`curl.exe -s http://127.0.0.1:9223/json/version`）

### 3. Session 过期

```
页面跳转到登录页
```

✅ 重新登录 ERP（手机号+密码+图形验证码）

### 4. 部署后第一次跑全部拒绝

合规审查的 LLM 可能比较严格，这是正常行为。可以：
- 用 `--products 货源ID1,货源ID2` 跳过审查直接处理指定商品
- 或者先采集一批更合适的商品

## 十、验证清单

| 项目 | 检查方式 |
|------|----------|
| Python 3.12 | `python --version` |
| Chrome 9223 | `curl.exe -s http://127.0.0.1:9223/json/version` |
| ERP 登录 | 访问采集箱看到商品列表 |
| API Key 有效 | 文本模型和视觉模型分别验证一次 |
| Playwright 可用 | `playwright install chromium` |
| 项目路径正确 | `cd` 到项目目录执行 `ls` |
| .env 存在 | `Get-Content .env` 检查4个key都有值 |
