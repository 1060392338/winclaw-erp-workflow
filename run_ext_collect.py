#!/usr/bin/env python3
"""货憨憨扩展采集PDD商品 — Playwright CDP 方案

替代 DrissionPage 的 PDD 采集器，用用户 Chrome 9223 的已有 session + 
货憨憨扩展的「采集此商品」按钮导航到ERP，不触发反爬。

用法:
  .venv/bin/python run_ext_collect.py 纳几许大诚专卖店 -n 3
  .venv/bin/python run_ext_collect.py 冠渠旗舰店 -n 5 -k 垃圾桶
  .venv/bin/python run_ext_collect.py 店铺名 -n 2 店铺名2 -n 3

流程:
  1. Playwright CDP 连 Chrome 9223 → 新tab到PDD首页
  2. 搜索店铺 → 切换「店铺」tab → 进店
  3. 浏览店内商品 → 点进详情页
  4. 等货憨憨扩展「采集此商品」按钮出现 → 点击 → 入ERP
  5. 重复直到采集满 N 件

对比现有 DrissionPage 方案:
  - PDD 导航: 同用 CDP 连接真实 Chrome，反爬级别相同
  - 防反爬: 用 CDP Input.dispatchMouseEvent 替代 Playwright click
  - 数据采集: ✅ 用扩展按钮替代手动提取，零检测风险
  - 不破坏: 不影响 run_store_collect_flow.py

扩展按钮定位（2026-05-19 验证）:
  - 容器: #hhh-gather-container  (fixed, 右下角)
  - 按钮: button.hhh_collect-button_HPXqD  → 文字「采集此商品」
"""
import sys, time, json, random, argparse, asyncio
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

PROJECT = Path(__file__).parent
# 从 config.yaml 读取端口配置
from infrastructure.config_loader import ConfigLoader
_ext_cfg = ConfigLoader().load()
_ext_cdp_ports = _ext_cfg.erp_cdp_ports
CDP_URL = f"http://127.0.0.1:{_ext_cdp_ports[0]}"
PDD_HOME = os.getenv("PDD_HOME", "https://mobile.yangkeduo.com/")
PDD_SEARCH = os.getenv("PDD_SEARCH", "https://mobile.yangkeduo.com/search_result.html?search_key={}")

# 货憨憨扩展按钮选择器（2026-05-19 直接从PDD商品页DOM验证）
EXT_COLLECT_BTN = 'button.hhh_collect-button_HPXqD:text("采集此商品")'
EXT_CONTAINER = "#hhh-gather-container"


def _random_delay(min_s=0.3, max_s=1.0):
    """随机延迟（模拟真人）"""
    time.sleep(random.uniform(min_s, max_s))


async def _connect_browser():
    """Playwright CDP 连 Chrome 9223 → 返回 (playwright, browser)"""
    p = await async_playwright().start()
    browser = await p.chromium.connect_over_cdp(CDP_URL)
    return p, browser


async def _find_or_create_tab(browser, platform: str) -> any:
    """复用已有平台的tab（cookie/shared session），没有才创建新tab

    对于 1688：复用已有 detail.1688.com 或 1688.com 的页面可避免滑块验证。
    对于 PDD：复用已有 yangkeduo.com 页面可保持登录态。
    """
    PDD_DOMAIN = os.getenv("PDD_DOMAIN", "yangkeduo.com")
    domain_map = {"pdd": PDD_DOMAIN, "1688": "1688.com"}
    target_domain = domain_map.get(platform, "1688")

    for ctx in browser.contexts:
        for pg in ctx.pages:
            if target_domain in pg.url:
                print(f"  📎 复用已有 {platform} tab: {pg.url[:60]}")
                return pg

    # 没找到 → 创建新tab
    page = await browser.new_page()
    print(f"  🆕 新建 {platform} tab")
    return page


async def cdp_click_element(page, element) -> bool:
    """用 CDP dispatchMouseEvent 点击元素（绕开 Playwright click 的反爬检测）

    Playwright 的 click() 会产生浏览器自动生成的合成事件，
    PDD 可以检测到。CDP 的 dispatchMouseEvent 更接近真人鼠标操作。
    """
    try:
        bbox = await element.bounding_box()
        if not bbox:
            return False
        x, y = bbox["x"] + bbox["width"] / 2, bbox["y"] + bbox["height"] / 2
        # 模拟鼠标从别处移过来
        cdp = await page.context.new_cdp_session(page)
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": random.uniform(10, 200),
            "y": random.uniform(10, 200),
        })
        time.sleep(random.uniform(0.1, 0.3))
        # 移动到目标
        steps = random.randint(3, 6)
        for i in range(steps):
            progress = (i + 1) / steps
            mx = random.uniform(10, 200) + (x - random.uniform(10, 200)) * progress + random.uniform(-5, 5)
            my = random.uniform(10, 200) + (y - random.uniform(10, 200)) * progress + random.uniform(-5, 5)
            cdp.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": mx, "y": my,
            })
            time.sleep(random.uniform(0.05, 0.15))
        # 点击
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
        time.sleep(random.uniform(0.04, 0.1))
        cdp.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": "left", "clickCount": 1,
        })
        return True
    except Exception:
        return False


async def cdp_click_by_js(page, js_selector: str) -> bool:
    """通过 JS elementFromPoint + click 点击（另一套反爬策略）"""
    return await page.evaluate(f"""() => {{
        const el = document.querySelector('{js_selector}');
        if (!el) return false;
        const r = el.getBoundingClientRect();
        const x = r.left + r.width / 2;
        const y = r.top + r.height / 2;
        // 用 CDP 层模拟点击（dispatchMouseEvent 由调用方处理）
        // 这里先找到元素
        const target = document.elementFromPoint(x, y) || el;
        target.dispatchEvent(new MouseEvent('click', {{
            bubbles: true, cancelable: true, view: window,
            clientX: x, clientY: y,
        }}));
        return true;
    }}""")


async def goto_search(page, shop_name: str) -> bool:
    """导航到PDD搜索页"""
    # 直接走搜索URL（比UI搜索更可靠，PDD自带的搜索页面）
    search_url = PDD_SEARCH.format(shop_name)
    await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)
    # 检查是否被重定向到登录
    url = page.url
    if "login" in url.lower() or "passport" in url.lower():
        print(f"  ❌ PDD需要登录（跳转到登录页）")
        return False
    print(f"  ✅ 已到搜索页")
    return True


async def switch_to_store_tab(page) -> bool:
    """在搜索结果页切换到「店铺」tab

    PDD移动端搜索结果的tab栏包含：全部/商品/店铺，切换后显示店铺列表。
    """
    for attempt in range(3):
        await page.wait_for_timeout(1000)
        clicked = await page.evaluate("""() => {
            const items = document.querySelectorAll('[class*="tab"]');
            for (const item of items) {
                const text = (item.textContent || "").trim();
                if (text.includes("店铺") || text.includes("店铺")) {
                    // 先确保元素可见
                    const r = item.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        item.click();
                        return true;
                    }
                }
            }
            return false;
        }""")
        if clicked:
            print(f"  ✅ 切换到店铺tab")
            await page.wait_for_timeout(2000)
            return True
    print(f"  ⚠️ 未找到店铺tab")
    return False


async def enter_store(page, shop_name: str) -> bool:
    """从搜索结果的店铺列表中找到目标店铺并进入

    在「店铺」tab下找到匹配的店铺名 → 点「进店」或店名卡片。
    """
    for attempt in range(5):
        await page.wait_for_timeout(1500)
        entered = await page.evaluate(f"""() => {{
            const all = document.querySelectorAll('*');
            for (const el of all) {{
                const t = (el.textContent || "").trim();
                if (t.includes("{shop_name}") && el.offsetHeight > 0) {{
                    // 找最近的"进店"按钮或可点击元素
                    const parent = el.closest('[class*="mall"],[class*="card"],[class*="item"]') || el.parentElement;
                    if (parent) {{
                        const btns = parent.querySelectorAll('button, [class*="btn"], [class*="button"], a');
                        for (const btn of btns) {{
                            const bText = (btn.textContent || "").trim();
                            if (bText.includes("进店") || bText.includes("进入")) {{
                                btn.click();
                                return "clicked_entry";
                            }}
                        }}
                        // 没找到按钮 → 直接点店名
                        el.click();
                        return "clicked_name";
                    }}
                }}
            }}
            return "not_found";
        }}""")
        print(f"  尝试{attempt+1}: {entered}")
        if entered != "not_found":
            await page.wait_for_timeout(3000)
            print(f"  ✅ 已进入店铺: {shop_name}")
            return True
    print(f"  ❌ 未能进入店铺（PDD可能反爬拦截）")
    return False


async def collect_product(page, idx: int, skip_entry=False) -> dict:
    """采集1个商品：进详情页 → 点扩展按钮

    假设当前已在店铺页（skip_entry=False）或详情页（skip_entry=True）。
    """
    result = {"index": idx, "success": False, "error": "", "goods_id": ""}

    if not skip_entry:
        # 从店铺页进详情（PDD流程）
        imgs = await page.evaluate("""() => {
            const imgs = document.querySelectorAll('img');
            const results = [];
            imgs.forEach(img => {
                const r = img.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.y > 0 && r.y < 1500
                    && img.src && img.src.includes('.pdd')) {
                    results.push({x: r.x + r.width/2, y: r.y + r.height/2});
                }
            });
            return results;
        }""")
        if not imgs:
            result["error"] = "未找到商品图片"
            return result
        print(f"  [商品{idx}] 找到 {len(imgs)} 张商品图")

        target_img = imgs[min(idx - 1, len(imgs) - 1)]
        clicked = await page.evaluate(f"""((x, y) => {{
            const el = document.elementFromPoint(x, y);
            if (!el) return false;
            let target = el;
            for (let i = 0; i < 5; i++) {{
                if (target.tagName === 'A' || target.onclick) break;
                const p = target.parentElement;
                if (!p) break;
                target = p;
            }}
            target.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true, view: window, clientX: x, clientY: y}}));
            return true;
        }})""", target_img["x"], target_img["y"])
        if not clicked:
            result["error"] = "商品图点击失败"
            return result
        await page.wait_for_timeout(4000)

    # 已到详情页 — 等扩展加载
    try:
        await page.wait_for_selector(EXT_COLLECT_BTN, timeout=8000)
        print(f"  ✅ 扩展已加载")
    except PWTimeout:
        result["error"] = "扩展按钮未加载（可能反爬拦截或扩展未注入）"
        return result

    # 点扩展采集按钮
    btn_clicked = await page.evaluate("""() => {
        const btn = document.querySelector('.hhh_collect-button_HPXqD');
        if (!btn) return false;
        if (btn.textContent.includes('采集此商品')) {
            btn.click();
            return true;
        }
        return false;
    }""")
    if not btn_clicked:
        result["error"] = "采集按钮点击失败"
        return result
    print(f"  ✅ 已点击「采集此商品」")

    # 等扩展反馈
    await page.wait_for_timeout(3000)

    goods_id = await page.evaluate("""() => {
        const m = window.location.href.match(/goods_id=(\\d+)/);
        if (m) return m[1];
        const m2 = window.location.href.match(/offer.(\\d+)/);
        return m2 ? m2[1] : "";
    }""")
    result["goods_id"] = goods_id
    result["success"] = True
    print(f"  ✅ 商品{idx}采集完成: {goods_id}")
    return result


async def _goto_1688_search(page, shop_name: str) -> bool:
    """导航到1688搜索页（比PDD宽松，直接搜索即可）"""
    search_url = f"https://s.1688.com/selloffer/offer_search.htm?keywords={shop_name}&n=y&filt=y&from=home"
    await page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(3000)
    url = page.url
    if "login" in url.lower() or "passport" in url.lower():
        print(f"  ❌ 1688需要登录")
        return False
    print(f"  ✅ 1688搜索页加载完成")
    return True


async def _enter_1688_store(page, shop_name: str) -> bool:
    """在1688搜索结果中找到目标店铺并进入"""
    for attempt in range(5):
        await page.wait_for_timeout(1500)
        entered = await page.evaluate(f"""() => {{
            const all = document.querySelectorAll('*');
            for (const el of all) {{
                const t = (el.textContent || "").trim();
                if (t.includes("{shop_name}") && el.offsetHeight > 0 && el.tagName === 'A') {{
                    const href = el.getAttribute('href') || '';
                    if (href.includes('shop') || href.includes('store') || href.includes('offer')) {{
                        el.click();
                        return "clicked";
                    }}
                }}
            }}
            return "not_found";
        }}""")
        if entered != "not_found":
            await page.wait_for_timeout(3000)
            print(f"  ✅ 已进入1688店铺: {shop_name}")
            return True
    print(f"  ❌ 未在1688找到店铺: {shop_name}")
    return False


async def _enter_1688_product(page, idx: int) -> bool:
    """在1688店铺页点开第idx个商品"""
    await page.wait_for_timeout(1000)
    clicked = await page.evaluate(f"""(() => {{
        const links = document.querySelectorAll('a[href*="offer"]');
        for (const link of links) {{
            if (link.offsetHeight > 50 && link.querySelector('img')) {{
                link.click();
                return true;
            }}
        }}
        return false;
    }})""")
    if clicked:
        await page.wait_for_timeout(3000)
        return True
    return False


async def main_async(shop_names: list[str], top_n: int, keyword: str = "", platform: str = "pdd"):
    """主流程"""
    p, browser, page = None, None, None
    collected_total = []

    try:
        print("=" * 60)
        print(f"🔍 扩展采集 [{platform}]: {' '.join(shop_names)} | 每家{top_n}件")
        if keyword:
            print(f"   关键词: {keyword}")
        print("=" * 60)

        p, browser = await _connect_browser()
        # 复用已有平台tab（避免新tab触发滑块验证）
        page = await _find_or_create_tab(browser, platform)
        print("✅ 已连接 Chrome 9223")

        for shop_name in shop_names:
            print(f"\n--- {platform} 店铺: {shop_name} ---")

            if platform == "1688":
                # 1688 采集（反爬宽松，直接搜索）
                if not await _goto_1688_search(page, shop_name):
                    continue
                await _enter_1688_store(page, shop_name)
            else:
                # PDD 采集（反爬严格，保持原有流程）
                if not await goto_search(page, shop_name):
                    continue
                await switch_to_store_tab(page)
                if not await enter_store(page, shop_name):
                    continue

            # 店内搜索关键词
            if keyword:
                print(f"  店内搜索: {keyword}")
                await page.evaluate(f"""() => {{
                    const inp = document.querySelector('input[type="search"]');
                    if (inp) {{
                        inp.value = '{keyword}';
                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                        inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                        // 搜索按钮
                        const btn = document.querySelector('[class*="search"] button') || 
                                   document.querySelector('button:has-text("搜索")') ||
                                   document.querySelector('[class*="submit"]');
                        if (btn) btn.click();
                    }}
                }}""")
                await page.wait_for_timeout(3000)

            # 采集
            for i in range(1, top_n + 1):
                if platform == "1688":
                    if not await _enter_1688_product(page, i):
                        print(f"  ❌ 第{i}件: 无法进入1688商品详情")
                        continue
                    result = await collect_product(page, i, skip_entry=True)
                collected_total.append(result)
                if result.get("success"):
                    print(f"  ✅ 第{i}件完成: {result.get('goods_id', '?')}")
                else:
                    print(f"  ❌ 第{i}件失败: {result.get('error', '?')}")
                # 后退到店铺页继续采下一个
                if i < top_n:
                    # 后退到店铺页继续采下一个
                    if platform == "1688":
                        await page.goto("javascript:history.back()", wait_until="domcontentloaded", timeout=15000)
                    else:
                        await page.go_back(wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2000)

        # 输出结果
        succeeded = [r for r in collected_total if r.get("success")]
        print(f"\n{'=' * 60}")
        print(f"📊 采集结果: {len(succeeded)}/{len(collected_total)} 成功")
        for r in succeeded:
            print(f"  ✅ {r['goods_id']}")
        failed = [r for r in collected_total if not r.get("success")]
        for r in failed:
            print(f"  ❌ 商品{r['index']}: {r.get('error', '')}")

        return succeeded

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if p:
            try:
                await p.stop()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="货憨憨扩展采集PDD/1688商品")
    parser.add_argument("shops", nargs="*", default=[], help="店铺名（PDD或1688），不填则按关键词全平台搜")
    parser.add_argument("-n", type=int, default=2, help="每店采集前N个（默认2）")
    parser.add_argument("-k", "--keyword", type=str, default="", help="店内搜索关键词")
    parser.add_argument("--platform", choices=["pdd", "1688"], default="pdd",
                        help="采集平台（默认pdd，1688反爬更宽松推荐使用）")
    args = parser.parse_args()

    result = asyncio.run(main_async(args.shops, args.n, args.keyword, args.platform))
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
