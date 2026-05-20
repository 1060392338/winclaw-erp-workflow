# infrastructure — 共享基础设施层
# 所有工作流共用，新增工作流不碰此目录
#
# 模块:
#   browser.py           浏览器管理（Playwright connect_over_cdp + CDP）
#   pdd_collector.py     PDD商品采集器
#   erp_publisher.py     ERP认领+Shopee发布
#   image_checker.py     图片合规检查（OCR + LLM Vision）
#   taiwan_regulation.py 台湾法规知识库
#   title_optimizer.py   标题优化（LLM驱动）
