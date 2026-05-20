"""采集器抽象基类 — 所有采集源(PDD/1688/Taobao等)的统一接口

设计原则:
  - 通用化: 新采集源只需继承 BaseCollector，不改动 Agent/Graph 代码
  - 接口统一: 所有采集源暴露相同的 collect_one/search_and_collect/connect/close
  - 反爬解耦: 反爬策略由子类实现，基类不管具体平台

扩展方式:
  1. 创建 infrastructure/collectors/xxx_collector.py 继承 BaseCollector
  2. 在 services/registry.py 注册: register_collector("xxx", XxxCollector)
  3. WorkflowState 中设置 collection_source="xxx" 即可切换
"""

import tempfile
from abc import ABC, abstractmethod
from typing import Optional


class BaseCollector(ABC):
    """采集器抽象基类

    所有采集源必须实现以下方法:
      - connect(): 连接浏览器/建立会话
      - close(): 清理资源
      - collect_one(): 采集1个商品
      - search_and_collect(keyword): 搜索采集1个商品
    """

    # 子类必须覆盖的类属性
    PLATFORM: str = ""           # 平台标识: "pdd", "1688", "taobao"
    PLATFORM_NAME: str = ""      # 平台中文名: "拼多多", "1688", "淘宝"

    def __init__(self, user_data_path: str = ""):
        self.user_data_path = user_data_path or tempfile.gettempdir()

    # === 抽象方法（子类必须实现） ===

    @abstractmethod
    def connect(self):
        """连接浏览器/建立会话

        子类自行决定连接方式:
          - DrissionPage 自启Chrome
          - Playwright connect_over_cdp
          - API session (如果平台允许)
        """
        ...

    @abstractmethod
    def close(self):
        """清理资源（关闭浏览器/断开连接）"""
        ...

    @abstractmethod
    def collect_one(self) -> dict:
        """采集1个商品

        Returns:
            {"goods_id": "...", "title": "...", "price": "...", "collected": True}
            或 {"error": "错误描述"}
        """
        ...

    @abstractmethod
    def search_and_collect(self, keyword: str) -> dict:
        """搜索关键词采集1个商品

        Args:
            keyword: 搜索关键词

        Returns:
            {"goods_id": "...", "title": "...", "price": "...", "collected": True}
            或 {"error": "错误描述"}
        """
        ...

    # === 可选覆盖 ===

    def collect_from_store(self, store_id: str) -> dict:
        """从店铺页采集（可选）

        Args:
            store_id: 平台店铺ID（如PDD的mall_id）
        """
        return {"error": f"{self.PLATFORM_NAME}不支持店铺直连采集"}

    def verify_collection(self) -> list[dict]:
        """验证ERP采集箱中已采集的商品（可选）"""
        return []

    # === 工具方法 ===

    def _make_result(self, goods_id: str = "", title: str = "",
                     price: str = "", collected: bool = False,
                     error: str = "", **kwargs) -> dict:
        """统一构造返回结果，自动填充 platform"""
        base = {"platform": self.PLATFORM, "goods_id": goods_id,
                "title": title, "price": price, "collected": collected}
        if error:
            base["error"] = error
        base.update(kwargs)
        return base
