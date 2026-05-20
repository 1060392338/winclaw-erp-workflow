"""配置加载器 — YAML config.yaml 解析 + 跨平台Chrome路径自动检测

用法:
    loader = ConfigLoader("config/config.yaml")
    config = loader.load()
    print(config.erp_url, config.stores)
"""

import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class StoreConfig:
    """店铺配置"""
    id: str
    name: str
    platform: str = "Shopee"
    region: str = ""


@dataclass
class AppConfig:
    """应用配置 — 所有业务配置的入口"""
    # ERP
    erp_url: str = "https://www.huohanhan.com"
    erp_cdp_ports: list[int] = field(default_factory=lambda: [9223, 9222, 9229, 9224])

    # 店铺
    stores: list[StoreConfig] = field(default_factory=list)

    # 浏览器
    chrome_path: str = ""
    chrome_user_data_dir: str = ""
    remote_debugging_port: int = 9223

    # PDD反爬
    pdd_delay_min: float = 2.0
    pdd_delay_max: float = 5.0
    pdd_mouse_steps: int = 3

    # LLM（默认值跟随 .env，不在此硬编码）
    image_model: str = "qwen3-vl-plus"
    text_model: str = "deepseek-v4-flash"
    light_model: str = "deepseek-v4-flash"
    temperature_decision: float = 0.3
    temperature_creative: float = 0.7
    ocr_confidence_threshold: float = 0.8

    # 合规
    banned_keywords: list[str] = field(default_factory=list)

    # 采集
    max_per_shop: int = 50
    collection_max_total: int = 100

    # 数据
    data_base_dir: str = "data"

    # 运行时
    runtime_platform: str = "openclaw"


class ConfigLoader:
    """配置加载器"""

    # Chrome 路径检测（按OS）
    _CHROME_PATHS = {
        "Darwin": [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ],
        "Windows": [
            "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%USERPROFILE%\AppData\Local\Google\Chrome\Application\chrome.exe"),
        ],
        "Linux": [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ],
    }

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = config_path

    def load(self) -> AppConfig:
        """加载配置，缺失字段用默认值"""
        raw = self._read_yaml()
        return self._build_config(raw)

    def _read_yaml(self) -> dict:
        """读取YAML文件"""
        try:
            import yaml
            path = Path(self.config_path)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        except ImportError:
            pass
        except Exception as e:
            print(f"[ConfigLoader] 读取配置失败: {e}", file=sys.stderr)
        return {}

    def _build_config(self, raw: dict) -> AppConfig:
        """从raw dict构建AppConfig"""
        c = AppConfig()

        # ERP
        erp = raw.get("erp", {})
        c.erp_url = erp.get("url", c.erp_url)
        c.erp_cdp_ports = erp.get("cdp_ports", c.erp_cdp_ports)

        # 店铺
        stores_raw = raw.get("stores", [])
        c.stores = [
            StoreConfig(
                id=s.get("id", ""),
                name=s.get("name", ""),
                platform=s.get("platform", "Shopee"),
                region=s.get("region", ""),
            )
            for s in stores_raw
        ]

        # 浏览器
        browser = raw.get("browser", {})
        c.chrome_path = browser.get("chrome_path", "") or self._detect_chrome_path() or ""
        c.chrome_user_data_dir = browser.get("user_data_dir", "")
        c.remote_debugging_ports = browser.get(
            "remote_debugging_ports", c.erp_cdp_ports
        )
        c.pdd_delay_min = browser.get("pdd_delay_min", c.pdd_delay_min)
        c.pdd_delay_max = browser.get("pdd_delay_max", c.pdd_delay_max)
        c.pdd_mouse_steps = browser.get("pdd_mouse_move_steps", c.pdd_mouse_steps)

        # LLM
        llm = raw.get("llm", {})
        c.image_model = llm.get("image_model", c.image_model)
        c.text_model = llm.get("text_model", c.text_model)
        c.light_model = llm.get("light_model", c.light_model)
        c.temperature_decision = llm.get("temperature_decision", c.temperature_decision)
        c.temperature_creative = llm.get("temperature_creative", c.temperature_creative)
        c.ocr_confidence_threshold = llm.get("ocr_confidence_threshold", c.ocr_confidence_threshold)

        # 合规
        compliance = raw.get("compliance", {})
        c.banned_keywords = compliance.get("banned_keywords", [])

        # 采集限制
        collection = raw.get("collection", {})
        c.max_per_shop = collection.get("max_per_shop", c.max_per_shop)
        c.collection_max_total = collection.get("max_total", c.collection_max_total)

        # 数据
        data = raw.get("data", {})
        c.data_base_dir = data.get("base_dir", c.data_base_dir)

        # 运行时
        runtime = raw.get("runtime", {})
        c.runtime_platform = runtime.get("platform", c.runtime_platform)

        return c

    @classmethod
    def _detect_chrome_path(cls) -> Optional[str]:
        """检测当前OS的Chrome路径"""
        return cls._detect_chrome_path_for_os(platform.system())

    @classmethod
    def _detect_chrome_path_for_os(cls, os_name: str) -> Optional[str]:
        """按OS名检测Chrome路径"""
        for candidate in cls._CHROME_PATHS.get(os_name, []):
            if os.path.exists(candidate):
                return candidate
        return None
