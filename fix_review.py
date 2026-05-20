#!/usr/bin/env python3
import sys
sys.stdout.reconfigure(encoding='utf-8')

path = r"C:\Users\Administrator\.openclaw\workspace\cross-border-erp-agent-new\infrastructure\compliance_checker.py"

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# The entire _review_one method to replace
old_start = '    def _review_one(self, product: Product) -> ComplianceResult:'
idx = content.find(old_start)
if idx < 0:
    print("ERROR: _review_one not found")
    sys.exit(1)

# Find the next method definition after _review_one
rest = content[idx + len(old_start):]
next_method = rest.find('\n    def ')
if next_method < 0:
    print("ERROR: no next method found")
    sys.exit(1)

# The old _review_one body ends at next_method
old_body_end = idx + len(old_start) + next_method
old_method = content[idx:old_body_end]

new_method = '''    def _review_one(self, product: Product) -> ComplianceResult:
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

        if not title_issues:
            return ComplianceResult(
                product=product,
                image_compliant=True,
                title_compliant=True,
                image_issues=[],
                title_issues=[],
                final_status="pass",
            )

        # 3. 标题违规 -> LLM优化标题
        try:
            optimized = self.title_optimizer.optimize(
                title=product.title,
                issues=title_issues,
            )
        except Exception:
            import logging
            logging.warning(f"标题优化失败 [{product.title[:30]}]: 降级为原文")
            optimized = product.title

        return ComplianceResult(
            product=product,
            image_compliant=True,
            title_compliant=False,
            image_issues=[],
            title_issues=title_issues,
            optimized_title=optimized,
            final_status="title_optimized",
        )
'''

content = content[:idx] + new_method + content[old_body_end:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("REPLACED OK")
