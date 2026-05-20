"""标题优化 — LLM驱动，台湾口语化 + 广告法合规

规则：
1. 删除违禁词（调用 TaiwanRegulation）
2. LLM（deepseek-v4-flash）优化：台湾口语化 + 繁体转换 + 营销优化
3. 80字截断
"""

class TitleOptimizer:
    """标题优化器 — LLM驱动"""

    OPTIMIZE_PROMPT = """你是台湾电商运营专家。优化以下商品标题以适合台湾Shopee市场。

规则：
1. 删除以下违禁关键词：{banned}
2. 转为地道的台湾用语（大陆用语→台湾用语，如"高质量"→"高品質"、"性价比"→"CP值"）
3. 转为繁体中文
4. 控制在80字以内

原始标题：{title}

返回JSON: {{"optimized": "优化后的标题", "changes": ["修改1", "修改2"]}}
只返回JSON，不要其他内容。"""

    MAX_TITLE_LENGTH = 80

    def __init__(self, regulation_checker=None):
        """可注入 TaiwainRegulation 实例"""
        self.regulation = regulation_checker

    def optimize(self, title: str, issues: list[str] = None) -> str:
        """优化标题
        
        Args:
            title: 原始标题
            issues: 违规项列表
            
        Returns:
            优化后的标题
        """
        # 1. 基础清理：删除违禁关键词
        cleaned = title
        if self.regulation:
            banned = self.regulation.get_banned_keywords()
            for kw in banned:
                cleaned = cleaned.replace(kw, "")

        if issues:
            for issue in issues:
                if "关键词:" in issue:
                    kw = issue.split("关键词:")[-1].strip().rstrip(")")
                    cleaned = cleaned.replace(kw, "")

        import re
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return ""

        # 2. LLM优化
        try:
            from infrastructure.llm_client import get_llm_client
            banned_str = ", ".join(self.regulation.get_banned_keywords()[:10]) if self.regulation else ""
            # 安全模板：用 str.format() 避免 title 中含 {banned} 等占位符时注入
            prompt = self.OPTIMIZE_PROMPT.replace("{banned}", banned_str).replace("{title}", cleaned)

            client = get_llm_client()
            resp = client.chat_json(
                messages=[{"role": "user", "content": prompt}],
                model=None,  # 从 .env 读取
                temperature=0.7,
            )
            if not resp.get("parse_error") and not resp.get("error"):
                optimized = resp.get("optimized", cleaned)
            else:
                optimized = cleaned
        except Exception:
            optimized = cleaned

        # 3. 80字截断
        if len(optimized) > self.MAX_TITLE_LENGTH:
            optimized = optimized[:self.MAX_TITLE_LENGTH]

        return optimized
