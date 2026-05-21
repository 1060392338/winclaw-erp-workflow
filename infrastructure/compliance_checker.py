"""合规审查 — 纯LLM内部判断，不操作ERP网页
支持并发审查（ThreadPoolExecutor），适合 20+ 商品批量场景。

用法:
    checker = ComplianceChecker(image_checker, regulation, title_optimizer)
    results = checker.review_batch_concurrent(products, max_workers=5)
    pass_ids = checker.get_pass_ids(results)
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import Callable, Optional
from models.schema import Product, ComplianceResult


class ComplianceChecker:
    """合规审查 — 纯LLM内部判断（支持并发）
    
    输入：采集好的 Product[] 列表
    输出：ComplianceResult[] — 只有final_status='pass'/'title_optimized'的进入认领发布
    
    不操作浏览器。所有判断在Python内存+LLM API中完成。
    """

    def __init__(self, image_checker, regulation_checker, title_optimizer):
        self.image_checker = image_checker       # ImageChecker (OCR + LLM Vision)
        self.regulation = regulation_checker     # TaiwanRegulation (法规知识库)
        self.title_optimizer = title_optimizer   # TitleOptimizer (LLM标题优化)

    # ─── 公共 API ───

    def review_batch(self, products: list[Product]) -> list[ComplianceResult]:
        """串行批量合规审查（向后兼容）"""
        return [self._review_one(p) for p in products]

    def review_batch_concurrent(
        self,
        products: list[Product],
        max_workers: int = 5,
        timeout: float = 60,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[ComplianceResult]:
        """并发批量合规审查

        Args:
            products: 商品列表
            max_workers: 并发线程数（默认 5，视觉 API 限流时建议 3）
            timeout: 单个商品超时（秒）
            on_progress: 进度回调 (done, total, product_title)

        Returns:
            ComplianceResult[]，顺序与输入 products 一致
        """
        total = len(products)
        results: list[Optional[ComplianceResult]] = [None] * total

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._review_one_safe, p, timeout): i
                for i, p in enumerate(products)
            }

            for future in as_completed(futures):
                idx = futures[future]
                product = products[idx]
                try:
                    result = future.result(timeout=timeout + 10)
                except TimeoutError:
                    result = ComplianceResult(
                        product=product,
                        image_compliant=False,
                        title_compliant=False,
                        image_issues=["审查超时"],
                        final_status="reject",
                    )
                except Exception as e:
                    result = ComplianceResult(
                        product=product,
                        image_compliant=False,
                        title_compliant=False,
                        image_issues=[f"审查异常: {e}"],
                        final_status="reject",
                    )
                results[idx] = result

                if on_progress:
                    done = sum(1 for r in results if r is not None)
                    on_progress(done, total, product.title[:30])

        return [r for r in results if r is not None]  # type: ignore

    # ─── 内部实现 ───

    def _review_one_safe(self, product: Product, timeout: float) -> ComplianceResult:
        """带超时保护的单商品审查"""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._review_one, product)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                return ComplianceResult(
                    product=product,
                    image_compliant=False,
                    title_compliant=False,
                    image_issues=[f"审查超时({timeout}s)"],
                    final_status="reject",
                )

    def _load_category_config(self) -> dict:
        """从外部配置文件读取类目列表"""
        import json
        from pathlib import Path
        cfg_file = Path(__file__).parent.parent / "config" / "category_list.json"
        default = {
            "categories": ["童裝", "五金", "百货", "3C", "服装", "食品", "美妆", "家居", "母婴", "户外", "宠物", "其他"],
            "keywords": {}
        }
        if cfg_file.exists():
            try:
                return json.loads(cfg_file.read_text(encoding='utf-8'))
            except Exception:
                pass
        return default

    def _identify_category(self, product: Product, image_description: str = "", vision_category: str = "") -> str:
        """用 DeepSeek flash 识别商品类目（从外部配置文件读取类目列表）"""
        if product.category:
            return product.category
        if vision_category:
            return vision_category

        cfg = self._load_category_config()
        categories = cfg.get("categories", ["其他"])
        category_list_str = "/".join(categories)

        try:
            from infrastructure.llm_client import get_llm_client
            import os
            client = get_llm_client()
            light_model = os.getenv("LLM_LIGHT_MODEL", "deepseek-v4-flash")
            prompt = f"你是一位电商商品类目识别专家。根据商品标题和图片描述，输出它的电商类目。只返回一个词：{category_list_str}。返回JSON格式：{{\"category\": \"类目名称\"}}"
            user_msg = f"标题：{product.title[:80]}"
            if image_description:
                user_msg += f"\n图片描述：{image_description}"
            result = client.chat_json(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}],
                model=light_model, temperature=0.1,
            )
            if isinstance(result, dict) and result.get("category"):
                return result["category"]
        except Exception:
            pass

        # 关键词兜底（从配置文件读取，不硬编码）
        title = product.title.lower()
        keywords = cfg.get("keywords", {})
        for cat, kws in keywords.items():
            if any(k.lower() in title for k in kws):
                return cat
        return "未分类"

    def _review_one(self, product: Product) -> ComplianceResult:
        """审查单个商品

        红线逻辑：
        1. 图片不合规 -> 直接 reject，不审标题
        2. 图片合规 + 标题合规 -> pass
        3. 图片合规 + 标题违规 -> LLM优化标题 -> title_optimized
        """
        # 1. 图片检查 - 第一道关
        try:
            image_result = self.image_checker.check(product.image_urls)
        except Exception as e:
            import logging
            logging.warning(f"图片检查异常 [{product.title[:30]}]: {e}")
            return ComplianceResult(
                product=product,
                image_compliant=False,
                title_compliant=False,
                image_issues=[f"图片检查失败: {e}"],
                final_status="reject",
            )

        if not image_result.compliant:
            return ComplianceResult(
                product=product,
                image_compliant=False,
                title_compliant=False,
                image_issues=image_result.issues,
                title_issues=[],
                final_status="reject",
            )

        # 2. 图片通过 -> 审查标题
        try:
            title_issues = self.regulation.check_title(product.title)
        except Exception as e:
            import logging
            logging.warning(f"标题检查异常 [{product.title[:30]}]: {e}")
            title_issues = []

        image_desc = getattr(image_result, 'vision_summary', '')
        vision_category = getattr(image_result, 'vision_category', '')

        if not title_issues:
            product.category = self._identify_category(product, image_description=image_desc, vision_category=vision_category)
            return ComplianceResult(
                product=product,
                image_compliant=True,
                title_compliant=True,
                image_issues=[],
                title_issues=[],
                final_status="pass",
            )

        # 3. 标题违规 -> 直接 reject（不做标题优化）
        print(f"  🚫 标题不合规，直接拒绝: {product.title[:40]}...", flush=True)
        return ComplianceResult(
            product=product,
            image_compliant=True,
            title_compliant=False,
            image_issues=[],
            title_issues=title_issues,
            final_status="reject",
        )

    def get_pass_ids(self, results: list[ComplianceResult]) -> list[str]:
        """提取pass商品的ERP ID列表"""
        return [
            r.product.erp_internal_id
            for r in results
            if r.final_status in ("pass", "title_optimized")
        ]

    def get_pass_products(self, results: list[ComplianceResult]) -> list[Product]:
        """提取可通过的商品列表"""
        return [
            r.product
            for r in results
            if r.final_status in ("pass", "title_optimized")
        ]

    def get_reject_count(self, results: list[ComplianceResult]) -> int:
        return sum(1 for r in results if r.final_status == "reject")

    def get_summary(self, results: list[ComplianceResult]) -> str:
        total = len(results)
        pass_count = sum(1 for r in results if r.final_status == "pass")
        optimized_count = sum(1 for r in results if r.final_status == "title_optimized")
        reject_count = self.get_reject_count(results)
        return (
            f"合规审查完成: {total}个商品\n"
            f"  通过: {pass_count}\n"
            f"  标题优化: {optimized_count}\n"
            f"  拒绝: {reject_count}"
        )
