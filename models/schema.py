"""跨境ERP多Agent自动化工作流 — 数据模型"""

from pydantic import BaseModel


class Product(BaseModel):
    """商品数据模型"""
    id: str = ""                       # ERP内商品ID
    title: str                         # 标题
    price: float                       # 价格
    shop_name: str                     # 来源店铺名
    category: str                      # 品类
    image_urls: list[str] = []         # 图片URL列表
    detail_url: str = ""               # 商品详情链接
    collected_at: str = ""             # 采集时间
    erp_internal_id: str = ""          # 在ERP采集箱中的内部标识


class ComplianceResult(BaseModel):
    """合规审查结果"""
    product: Product
    image_compliant: bool              # 图片是否合规
    title_compliant: bool              # 标题是否合规
    image_issues: list[str] = []       # 图片违规项
    title_issues: list[str] = []       # 标题违规项
    optimized_title: str = ""          # 优化后的标题
    final_status: str = ""             # pass / reject / title_optimized


class StoreTarget(BaseModel):
    """发布目标店铺"""
    store_id: str
    store_name: str
    platform: str = "Shopee"
