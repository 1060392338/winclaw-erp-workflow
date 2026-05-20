"""PDD商品采集器 — DP(DrissionPage)方案

继承 BaseCollector，实现 PDD 平台的采集逻辑。

🚨🚨🚨 反爬铁律（每次操作PDD前必须核验） 🚨🚨🚨

1. 【禁止调API】绝对不准对拼多多发起任何XHR/fetch/requests HTTP调用
2. 【纯连接模式】只连已有Chrome(`127.0.0.1:9223`)，不启动新浏览器
3. 【elementFromPoint点击】商品图点击进入详情页
4. 【img[src*=pddpic]找图】定位商品卡片用图片选择器
5. 【模拟真人操作】所有交互加随机延迟 + 滚动
6. 【不杀浏览器】绝不quit/close，连接断开=置None
7. 【DP run_js 铁规】所有JS必须顶格 return
8. 【登录态必须】搜索需有效Cookie

⚠️ 2026-05-17: PDD搜索已触发反爬("系统繁忙")，当前仅首页推荐流可用。
"""

import time
import random
import json
from typing import Optional
from urllib.parse import quote

from infrastructure.base_collector import BaseCollector


class PDDHomepageCollector(BaseCollector):
    """PDD采集器：首页推荐流 + 搜索页 + 店铺直连

    继承 BaseCollector，实现 PDD 平台特化的采集逻辑。
    所有JS调用遵循 DP run_js 铁规：必须顶格 return。
    """

    PLATFORM = "pdd"
    PLATFORM_NAME = "拼多多"

    PDD_HOME = "https://mobile.yangkeduo.com/"
    PDD_SEARCH = "https://mobile.yangkeduo.com/search_result.html?search_key={}"
    PDD_MALL = "https://mobile.yangkeduo.com/mall_page.html?mall_id={}"
    COLLECT_BTN = '[class*="hhh_collect-button"][type="primary"]'
    ERP_COLLECT_BOX = "https://www.huohanhan.com/member/product/general/collect-box"

    # 反爬参数
    SCROLL_PAUSES = 5
    SCROLL_RANGE = (300, 500)
    PAGE_LOAD_WAIT = 5
    DETAIL_WAIT = 4
    COLLECT_WAIT = 3

    def __init__(self, user_data_path: str = "",
                 connect_existing: bool = False, cdp_port: int = 9223):
        super().__init__(user_data_path)
        self._page = None
        self._connect_existing = connect_existing
        self._cdp_port = cdp_port

    # === BaseCollector 接口 ===

    def connect(self):
        """连接已有Chrome → 开新tab到PDD（保护ERP tab不受导航影响）"""
        from DrissionPage import ChromiumPage
        import time
        main = ChromiumPage(addr_or_opts=f"127.0.0.1:{self._cdp_port}")
        self._page = main.new_tab(self.PDD_HOME)
        time.sleep(self.PAGE_LOAD_WAIT)

    def close(self):
        """关闭PDD tab（不杀浏览器）"""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
        self._page = None

    def collect_one(self) -> dict:
        """首页推荐流采集1个商品"""
        self._ensure_connected()
        page = self._page
        page.get(self.PDD_HOME)
        time.sleep(self.PAGE_LOAD_WAIT)

        if self._check_login():
            return self._make_result(
                error="PDD需要登录", url=page.url)

        self._scroll_to_load()
        return self._do_collect_from_page("首页")

    def search_and_collect(self, keyword: str) -> dict:
        """搜索关键词采集1个商品

        ⚠️ 2026-05-17: PDD搜索已触发"系统繁忙"反爬，此方法可能不可用。
        降级策略: 返回错误提示，建议使用 collect_one() 首页采集。
        """
        self._ensure_connected()
        page = self._page

        search_url = self.PDD_SEARCH.format(quote(keyword))
        page.get(search_url)
        time.sleep(self.PAGE_LOAD_WAIT)

        if self._check_login():
            return self._make_result(
                error="PDD需要登录（Cookie过期，需手动短信验证码登录）",
                url=page.url)

        self._scroll_to_load()
        return self._do_collect_from_page(f"搜索'{keyword}'")

    def collect_from_store(self, store_id: str) -> dict:
        """mall_id直连店铺页采集1个商品"""
        self._ensure_connected()
        page = self._page
        page.get(self.PDD_MALL.format(store_id))
        time.sleep(self.PAGE_LOAD_WAIT)

        if self._check_login():
            return self._make_result(
                error="PDD需要登录（Cookie过期）", url=page.url)

        self._scroll_to_load()
        return self._do_collect_from_page(f"店铺(mall_id={store_id})")

    def verify_collection(self) -> list[dict]:
        """切到ERP采集箱验证未认领商品"""
        self._ensure_connected()
        page = self._page
        page.get(self.ERP_COLLECT_BOX)
        time.sleep(4)

        try:
            page.ele("text:未认领").click()
            time.sleep(2)
        except Exception:
            pass

        items_json = page.run_js("""
return (function() {
    var rows = document.querySelectorAll('table tbody tr');
    var result = [];
    rows.forEach(function(row) {
        var text = (row.textContent || '').trim();
        if (text && text !== '暂无数据') {
            var goodsId = text.match(/货源ID[：:]\\s*(\\d+)/);
            var t = text.match(/采集时间[：:]\\s*(.+?)(?:编辑|认领|删除|$)/);
            var p = text.match(/CNY\\s*([\\d.]+)/);
            result.push({
                goods_id: goodsId ? goodsId[1] : '',
                price: p ? p[1] : '',
                time: t ? t[1].trim() : '',
                raw: text.substring(0, 150)
            });
        }
    });
    return JSON.stringify(result);
})()
""")
        return json.loads(items_json) if items_json else []

    # === 内部方法 ===

    def _ensure_connected(self):
        if self._page is None:
            self.connect()

    def _check_login(self) -> bool:
        """检查是否被重定向到登录页 — 精确匹配PDD登录URL"""
        url = self._page.url.lower()
        # PDD 登录域名: passport.yangkeduo.com / passport.pinduoduo.com
        return any(domain in url for domain in [
            "passport.yangkeduo.com",
            "passport.pinduoduo.com",
            "login.yangkeduo.com",
        ])

    def _scroll_to_load(self):
        page = self._page
        for _ in range(self.SCROLL_PAUSES):
            page.scroll.down(random.randint(*self.SCROLL_RANGE))
            time.sleep(random.uniform(1.5, 2.5))

    def _find_product_images(self) -> list[dict]:
        result = self._page.run_js("""
return (function() {
    var imgs = document.querySelectorAll('img');
    var result = [];
    imgs.forEach(function(img) {
        var r = img.getBoundingClientRect();
        if (r.width > 150 && r.height > 150
            && r.y >= 0 && r.y < 800
            && img.src && img.src.indexOf('pddpic') > -1) {
            result.push({x: r.x+r.width/2, y: r.y+r.height/2});
        }
    });
    return JSON.stringify(result);
})()
""")
        return json.loads(result) if result else []

    def _enter_detail_page(self, img: dict) -> bool:
        page = self._page
        # 用 CDP dispatchTouchEvent 替代 MouseEvent.click()（PDD React 屏蔽鼠标事件）
        page.run_js(f"""
return (function() {{
    var el = document.elementFromPoint({img['x']}, {img['y']});
    if (!el) return false;
    for (var i=0; i<5; i++) {{
        if (el.tagName==='A' || el.onclick) break;
        if (el.parentElement) el = el.parentElement;
    }}
    // 触屏事件（PDD移动端必须用touch，MouseEvent被React屏蔽）
    var touch = new Touch({{
        identifier: Date.now(),
        target: el,
        clientX: {img['x']},
        clientY: {img['y']},
    }});
    el.dispatchEvent(new TouchEvent('touchstart', {{
        cancelable: true, bubbles: true,
        touches: [touch], targetTouches: [touch],
    }}));
    el.dispatchEvent(new TouchEvent('touchend', {{
        cancelable: true, bubbles: true,
        touches: [touch], targetTouches: [touch],
    }}));
    // 兜底：element.click()
    if (!document.querySelector('.pdd-header-price')) {{
        el.click();
    }}
    return true;
}})()
""")
        time.sleep(self.DETAIL_WAIT)
        return 'goods' in page.url

    def _extract_product_info(self) -> dict:
        page = self._page
        goods_id = page.run_js(
            "return (function() {"
            "var m=window.location.href.match(/goods_id=(\\d+)/);"
            "return m?m[1]:'';"
            "})()")
        title = page.run_js(
            "return (function() {"
            "var e=document.querySelector('[class*=\"title\"],[class*=\"name\"],h1');"
            "return e?e.textContent.replace(/[\\u200b]/g,'').trim().substring(0,100):'';"
            "})()")
        price = page.run_js(
            "return (function() {"
            "var e=document.querySelector('[class*=\"price\"],[class*=\"Price\"]');"
            "return e?e.textContent.replace(/[\\u200b]/g,'').trim().substring(0,20):'';"
            "})()")
        return {"goods_id": str(goods_id or ''),
                "title": str(title or ''),
                "price": str(price or '')}

    def _click_collect(self) -> bool:
        page = self._page
        time.sleep(2)
        clicked = page.run_js(
            "return (function() {"
            f"var btn=document.querySelector('{self.COLLECT_BTN}');"
            "if(btn){btn.click();return true;}return false;"
            "})()")
        time.sleep(self.COLLECT_WAIT)
        return bool(clicked)

    def _do_collect_from_page(self, source: str) -> dict:
        imgs = self._find_product_images()
        if not imgs:
            return self._make_result(
                error=f"{source}未找到商品图片（可能被反爬或页面未渲染）")

        if not self._enter_detail_page(imgs[0]):
            return self._make_result(
                error=f"{source}未进入详情页（可能被反爬拦截）")

        info = self._extract_product_info()
        if not info.get("goods_id"):
            return self._make_result(error="无法提取商品ID")

        if not self._click_collect():
            return self._make_result(
                platform=self.PLATFORM,
                error="未找到采集按钮（货憨憨扩展未加载或版本不匹配）",
                **info)

        return self._make_result(
            platform=self.PLATFORM, collected=True, **info)
