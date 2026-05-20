"""跨境ERP多Agent自动化工作流 — WorkflowState"""

from typing import TypedDict, Optional
from models.schema import Product, ComplianceResult, StoreTarget


class WorkflowState(TypedDict, total=False):
    session_id: str
    stage: str                         # 当前阶段

    # 用户输入
    user_shops: list[str]              # 拼多多店铺名（1-5个）
    user_category: str                 # 要采集的品类
    user_keyword: str                  # 搜索关键词（优先于shops）
    user_mall_id: str                  # PDD店铺mall_id（直连店铺页）
    collection_source: str             # 采集源: "pdd"|"1688"|"taobao"
    collection_limit: int              # 采集数量上限（默认1）
    collection_mode: str               # 采集模式: "search"|"homepage"|"store"

    # 采集阶段（拼多多页面）
    collected_products: list[Product]
    collection_errors: list[str]

    # 优化阶段（ERP采集箱页面内）
    compliance_results: list[ComplianceResult]
    compliant_product_ids: list[str]   # 合规商品在ERP中的ID
    rejected_product_ids: list[str]    # 被淘汰商品的ERP ID

    # 发布阶段（ERP页面内）
    available_stores: list[StoreTarget]
    selected_store: Optional[StoreTarget]
    publish_config_verified: bool      # 确认"暂不上架"已设置
    publish_results: list[dict]

    errors: list[str]
