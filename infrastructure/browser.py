"""浏览器管理 — Playwright connect_over_cdp + CDP Session 单引擎架构

连接用户本机Chrome（已登录PDD+ERP），通过CDP端口操作。
跨平台：Windows/Mac/Linux，自动检测Chrome路径。
"""

import random
import time
from typing import Optional
from playwright.sync_api import sync_playwright, Browser, Page, CDPSession


class BrowserManager:
    """Playwright connect_over_cdp 连接用户本机Chrome

    支持自动发现端口：不传 cdp_ports 时扫描 9222-9229，
    也可通过 config.yaml 的 cdp_ports 列表指定。
    """

    # 默认扫描的端口范围
    DEFAULT_SCAN_PORTS = list(range(9222, 9230))

    def __init__(self, cdp_ports: list[int] | None = None):
        self.cdp_ports = cdp_ports or list(self.DEFAULT_SCAN_PORTS)
        self._connected_port: int | None = None
        self._playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.cdp_session: Optional[CDPSession] = None

    @property
    def cdp_port(self) -> int:
        """当前已连接的端口（connect 成功后可用）"""
        if self._connected_port is None:
            return self.cdp_ports[0] if self.cdp_ports else 9223
        return self._connected_port

    @property
    def cdp_url(self) -> str:
        return f"http://127.0.0.1:{self.cdp_port}"

    def connect(self) -> Page:
        """尝试所有配置的端口，第一个能连上的用

        Raises:
            ConnectionError: 所有端口都连不上
        """
        last_error = None
        for port in self.cdp_ports:
            url = f"http://127.0.0.1:{port}"
            try:
                self._playwright = sync_playwright().start()
                self.browser = self._playwright.chromium.connect_over_cdp(url)
                self._connected_port = port
                break  # 连上了
            except Exception as e:
                if self._playwright:
                    try:
                        self._playwright.stop()
                    except Exception:
                        pass
                    self._playwright = None
                last_error = e
                continue

        if not self.browser:
            self.disconnect()
            ports_str = ", ".join(str(p) for p in self.cdp_ports)
            raise ConnectionError(
                f"无法连接到 Chrome CDP (尝试端口: {ports_str})。\n"
                f"请确保Chrome已启动：chrome --remote-debugging-port=<端口> --remote-allow-origins=*\n"
                f"或通过 --cdp-port 参数指定端口。"
            ) from last_error

        # 获取或创建主页面 — 优先使用采集箱页面（用户可能打开了多个标签页）
        contexts = self.browser.contexts
        if contexts and contexts[0].pages:
            # 找包含collect-box的页面，避免连到其他无关标签页
            pages = contexts[0].pages
            self.page = None
            for p in pages:
                if "collect-box" in p.url:
                    self.page = p
                    break
            if not self.page:
                self.page = pages[0]  # 没找到就用第一个
        else:
            self.page = contexts[0].new_page() if contexts else self.browser.new_context().new_page()

        # 创建CDP session
        self.cdp_session = self.page.context.new_cdp_session(self.page)

        return self.page

    def new_tab(self) -> Page:
        """创建新标签页"""
        if not self.browser:
            raise RuntimeError("请先调用 connect()")
        return self.browser.contexts[0].new_page()

    def find_tab_by_url(self, url_pattern: str) -> Optional[Page]:
        """在所有tab中查找匹配URL的页面"""
        if not self.browser:
            return None
        for page in self.browser.contexts[0].pages:
            if url_pattern in page.url:
                return page
        return None

    def wait_for_new_tab(self, existing_urls: set[str], timeout: float = 10) -> Optional[Page]:
        """等待新tab打开（基于existing URL set）"""
        if not self.browser:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            for page in self.browser.contexts[0].pages:
                if page.url not in existing_urls and page.url not in ("about:blank", ""):
                    time.sleep(1)  # 等页面加载
                    return page
            time.sleep(0.5)
        return None

    def screenshot(self, path: str):
        """截取当前页面的全页截图"""
        if self.page:
            self.page.screenshot(path=path, full_page=True)

    def touch(self, x: float, y: float):
        """CDP触屏事件（移动端PDD必须用触屏，React屏蔽鼠标事件）"""
        if not self.cdp_session:
            raise RuntimeError("请先调用 connect()")
        import random, time
        self.cdp_session.send("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [{"x": x, "y": y}],
        })
        time.sleep(random.uniform(0.03, 0.1))
        self.cdp_session.send("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [{"x": x, "y": y}],
        })

    def type_text(self, text: str):
        """CDP插入文本（绕开DOM input事件检测）"""
        if not self.cdp_session:
            raise RuntimeError("请先调用 connect()")
        self.cdp_session.send("Input.insertText", {"text": text})

    def scroll_down(self, px: int = None):
        """随机向下滚动"""
        if not self.cdp_session:
            raise RuntimeError("请先调用 connect()")
        import random, time
        dy = px or random.randint(250, 500)
        self.cdp_session.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": 200, "y": 400,
            "deltaX": 0, "deltaY": dy,
        })
        time.sleep(random.uniform(0.5, 1))

    def disconnect(self):
        """断开连接，停止Playwright（不关闭Chrome）"""
        try:
            if self.cdp_session:
                self.cdp_session.detach()
                self.cdp_session = None
            if self._playwright:
                self._playwright.stop()
                self._playwright = None
        except Exception as e:
            import logging
            logging.debug(f"BrowserManager.disconnect 清理异常: {e}")
        self.browser = None
        self.page = None


class CDPMouseSimulator:
    """CDP鼠标模拟 — 反爬核心

    在PDD等国内平台上，Playwright的 page.click() 会触发反爬检测。
    必须使用CDP Input.dispatchMouseEvent 模拟真人鼠标轨迹。
    """

    @staticmethod
    def _random_steps() -> int:
        """随机轨迹步数（2-5步）"""
        return random.randint(2, 5)

    @staticmethod
    def _random_delay(min_ms: int, max_ms: int) -> float:
        """随机延迟（毫秒 → 秒）"""
        return random.uniform(min_ms, max_ms) / 1000.0

    @staticmethod
    def _generate_path(start_x: float, start_y: float,
                       target_x: float, target_y: float,
                       steps: int) -> list[tuple[float, float]]:
        """生成多点鼠标轨迹

        每步含随机偏移（模拟手抖/微调），终点收敛到目标坐标。
        """
        path = []
        for i in range(steps):
            progress = (i + 1) / steps
            mx = start_x + (target_x - start_x) * progress + random.uniform(-8, 8)
            my = start_y + (target_y - start_y) * progress + random.uniform(-5, 5)
            path.append((mx, my))
        return path

    @classmethod
    def click(cls, cdp_session: CDPSession, x: float, y: float,
              delay_min: float = 0.2, delay_max: float = 0.5) -> None:
        """CDP鼠标点击（含随机停顿和press/release间隔）

        Args:
            cdp_session: Playwright CDPSession
            x: 目标X坐标
            y: 目标Y坐标
            delay_min: 点击前最小停顿（秒）
            delay_max: 点击前最大停顿（秒）
        """
        # 随机起点（模拟鼠标从远处移过来）
        start_x = random.uniform(10, 200)
        start_y = random.uniform(10, 200)

        # 生成轨迹并移动
        steps = cls._random_steps()
        path = cls._generate_path(start_x, start_y, x, y, steps)
        for mx, my in path:
            cdp_session.send("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": mx, "y": my
            })
            time.sleep(random.uniform(0.05, 0.15))

        # 点击前随机停顿
        time.sleep(random.uniform(delay_min, delay_max))

        # Press
        cdp_session.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": "left", "clickCount": 1
        })
        time.sleep(random.uniform(0.04, 0.1))

        # Release
        cdp_session.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": "left", "clickCount": 1
        })
