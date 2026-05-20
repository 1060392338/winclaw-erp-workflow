"""图片合规检查 — OCR文字识别 + LLM Vision形象分析

双引擎策略：
- pytesseract OCR → 快速提取图片中文字（简体/繁体/违禁词）
- qwe3.6plus Vision → 分析商品形象合规性，兜底OCR置信度不足
"""

from dataclasses import dataclass, field
from infrastructure.taiwan_regulation import TaiwanRegulation


@dataclass
class ImageCheckResult:
    """图片合规检查结果"""
    compliant: bool
    issues: list[str] = field(default_factory=list)
    ocr_text: str = ""
    ocr_confidence: float = 0.0
    vision_summary: str = ""


class ImageChecker:
    """图片合规检查器 — OCR + LLM Vision（含 SSRF/图片炸弹防护）"""

    VISION_PROMPT = """你是跨境电商合规审查专家。分析以下商品图片是否违反台湾市场规定。

检查项：
1. 图片中是否有违禁文字（最/第一/唯一/全网/国家级/治疗/减肥/美白/祛斑/特效等）
2. 商品形象是否适合台湾市场（无暴力/色情/政治敏感内容）
3. 包装标签是否有药品/保健品类宣称（台湾化妆品不可宣称医疗效果）
4. 是否有未授权的认证标志（BSMI/NCC/有机认证等需有证书）

返回JSON: {"compliant": true/false, "issues": ["违规项1", "违规项2"], "summary": "简要分析"}
只返回JSON，不要其他内容。"""

    MAX_IMAGE_PIXELS = 100_000_000  # 100M 像素防炸弹
    ALLOWED_SCHEMES = ("http", "https")
    BLOCKED_DOMAINS = ("127.0.0.1", "localhost", "::1", "0.0.0.0")

    def __init__(self, ocr_confidence_threshold: float = 0.8):
        self.confidence_threshold = ocr_confidence_threshold
        self.regulation = TaiwanRegulation()

    def check(self, image_urls: list[str]) -> ImageCheckResult:
        """检查商品图片合规性"""
        if not image_urls:
            return ImageCheckResult(compliant=True, issues=[])

        issues = []
        ocr_text_all = []
        lowest_confidence = 1.0

        # 过滤掉空URL
        valid_urls = [u for u in image_urls if u and u.startswith('http')]
        
        for url in valid_urls:
            ocr_result = self._ocr_image(url)
            ocr_text_all.append(ocr_result["text"])
            lowest_confidence = min(lowest_confidence, ocr_result["confidence"])
            ocr_issues = self._check_text_compliance(ocr_result["text"])
            issues.extend(ocr_issues)

        combined_text = " | ".join(filter(None, ocr_text_all))

        # OCR置信度不足 → 走Vision兜底（有有效URL才调）
        if (lowest_confidence < self.confidence_threshold or not combined_text) and valid_urls:
            vision_result = self._vision_check(valid_urls)
            if vision_result.get("issues"):
                issues.extend(vision_result["issues"])
            return ImageCheckResult(
                compliant=len(issues) == 0,
                issues=issues,
                ocr_text=combined_text,
                ocr_confidence=lowest_confidence,
                vision_summary=vision_result.get("summary", ""),
            )

        return ImageCheckResult(
            compliant=len(issues) == 0,
            issues=issues,
            ocr_text=combined_text,
            ocr_confidence=lowest_confidence,
        )

    def _safe_get_image(self, url: str):
        """安全获取图片 — URL校验 + 内网阻断"""
        from urllib.parse import urlparse
        import requests
        parsed = urlparse(url)
        if parsed.scheme not in self.ALLOWED_SCHEMES:
            raise ValueError(f"不允许的协议: {parsed.scheme}")
        hostname = (parsed.hostname or "").lower()
        if hostname in self.BLOCKED_DOMAINS or any(
            hostname.startswith(p) for p in (
                "127.", "10.", "192.168.", "172.16.", "172.17.",
                "172.18.", "172.19.", "172.20.", "172.21.", "172.22.",
                "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
                "172.28.", "172.29.", "172.30.", "172.31.", "169.254.",
            )
        ):
            raise ValueError(f"禁止访问内网地址: {hostname}")
        resp = requests.get(url, timeout=30, stream=True)
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > 50 * 1024 * 1024:
            resp.close()
            raise ValueError(f"图片过大: {content_length} bytes")
        return resp

    def _ocr_image(self, url: str) -> dict:
        """对单张图片执行OCR"""
        try:
            import pytesseract
            from PIL import Image
            import io

            resp = self._safe_get_image(url)
            img = Image.open(io.BytesIO(resp.content))
            if img.width * img.height > self.MAX_IMAGE_PIXELS:
                raise ValueError(f"图片像素过大: {img.width}x{img.height}")
            data = pytesseract.image_to_data(
                img, lang='chi_sim+chi_tra',
                output_type=pytesseract.Output.DICT
            )

            # 提取高置信度文字
            texts = []
            confidences = []
            for i, conf in enumerate(data.get("conf", [])):
                if isinstance(conf, (int, float)) and conf > 30:  # tesseract 返回 int
                    texts.append(data["text"][i])
                    confidences.append(conf / 100.0)

            combined = " ".join(t.strip() for t in texts if t.strip())
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
            return {"text": combined, "confidence": avg_conf}

        except Exception as e:
            import logging
            logging.warning(f"OCR提取异常: {e}")
            return {"text": "", "confidence": 0.0}

    def _check_text_compliance(self, text: str) -> list[str]:
        """检查OCR文字是否含违规内容"""
        return self.regulation.check_title(text)

    def _vision_check(self, image_urls: list[str]) -> dict:
        """LLM Vision 兜底分析（走阿里百炼 VISION_ENDPOINT）"""
        try:
            from infrastructure.llm_client import get_llm_client
            client = get_llm_client()
            return client.chat_json_vision(
                system_prompt=self.VISION_PROMPT,
                image_urls=image_urls[:3],  # 最多3张
                model=None,  # 从 .env 读取
                temperature=0.3,
            )
        except Exception as e:
            return {"issues": [f"Vision调用异常: {e}"], "summary": ""}
