"""图片合规检查 — OCR文字识别 + LLM Vision形象分析

双引擎策略：
- pytesseract OCR → 快速提取图片中文字（简体/繁体/违禁词）
- qwe3.6plus Vision → 分析商品形象合规性，兜底OCR置信度不足
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from infrastructure.taiwan_regulation import TaiwanRegulation


def _locate_tessdata() -> str:
    """查找可用的 tessdata 目录 — 项目目录 > 用户目录 > 安装目录"""
    project_tess = str(Path(__file__).resolve().parent.parent / "tessdata")
    candidates = [
        project_tess,                                              # ① 项目目录
        os.path.join(os.path.expanduser("~"), "tessdata"),         # ② 用户目录
        r"C:\Program Files\Tesseract-OCR\tessdata",                # ③ 安装目录
    ]
    for d in candidates:
        if os.path.isfile(os.path.join(d, "chi_sim.traineddata")):
            return d
    return candidates[-1]


@dataclass
class ImageCheckResult:
    """图片合规检查结果"""
    compliant: bool
    issues: list[str] = field(default_factory=list)
    ocr_text: str = ""
    ocr_confidence: float = 0.0
    vision_summary: str = ""
    vision_category: str = ""


class ImageChecker:
    """图片合规检查器 — OCR + LLM Vision（含 SSRF/图片炸弹防护）"""

    VISION_PROMPT = """你是跨境电商合规审查专家。分析以下商品图片是否违反台湾市场规定。

检查项：
1. 图片中是否有违禁文字（最/第一/唯一/全网/国家级/治疗/减肥/美白/祛斑/特效等）
2. 商品形象是否适合台湾市场（无暴力/色情/政治敏感内容）
3. 包装标签是否有药品/保健品类宣称（台湾化妆品不可宣称医疗效果）
4. 是否有未授权的认证标志（BSMI/NCC/有机认证等需有证书）

返回JSON: {"compliant": true/false, "issues": ["违规项1", "违规项2"], "summary": "简要分析", "image_description": "用一句话描述图片里是什么商品"}
只返回JSON，不要其他内容。"""

    MAX_IMAGE_PIXELS = 100_000_000  # 100M 像素防炸弹
    ALLOWED_SCHEMES = ("http", "https")
    BLOCKED_DOMAINS = ("127.0.0.1", "localhost", "::1", "0.0.0.0")

    def __init__(self, ocr_confidence_threshold: float = 0.8):
        self.confidence_threshold = ocr_confidence_threshold
        self.regulation = TaiwanRegulation()

    def check(self, image_urls: list[str], vision_mode: str = "auto") -> ImageCheckResult:
        """检查商品图片合规性

        Args:
            image_urls: 图片URL列表
            vision_mode: Vision调用策略
                - "auto": 原有逻辑（OCR置信度不足时自动调Vision）
                - "ocr_only": 只做OCR，不调Vision（供分层策略使用）
                - "always": OCR + 强制调Vision
        """
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

        # Vision调用逻辑（根据vision_mode控制）
        need_vision = False
        if vision_mode == "always" and valid_urls:
            need_vision = True
        elif vision_mode == "auto" and (lowest_confidence < self.confidence_threshold or not combined_text) and valid_urls:
            need_vision = True
        # vision_mode == "ocr_only" 时不调Vision

        if need_vision:
            vision_result = self._vision_check(valid_urls)
            if vision_result.get("issues"):
                issues.extend(vision_result["issues"])
            return ImageCheckResult(
                compliant=len(issues) == 0,
                issues=issues,
                ocr_text=combined_text,
                ocr_confidence=lowest_confidence,
                vision_summary=vision_result.get("summary", ""),
                vision_category=vision_result.get("vision_category", ""),
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

    # Tesseract 可执行文件路径（Windows 默认安装位置）
    _TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    # 语言包目录：项目目录 > 用户目录 > 安装目录（三级优先，模块级函数计算）
    _TESSDATA_PREFIX = _locate_tessdata()

    def _ocr_image(self, url: str) -> dict:
        """对单张图片执行OCR"""
        try:
            import pytesseract
            import os
            # 确保 tesseract_cmd 指向正确的可执行文件
            if os.path.isfile(self._TESSERACT_CMD):
                pytesseract.pytesseract.tesseract_cmd = self._TESSERACT_CMD
            if os.path.isdir(self._TESSDATA_PREFIX):
                os.environ.setdefault("TESSDATA_PREFIX", self._TESSDATA_PREFIX)
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
            result = client.chat_json_vision(
                system_prompt=self.VISION_PROMPT,
                image_urls=image_urls[:3],  # 最多3张
                model=None,  # 从 .env 读取
                temperature=0.3,
            )
            if isinstance(result, dict):
                return result
            return {"issues": [], "summary": "", "vision_category": ""}
        except Exception as e:
            return {"issues": [f"Vision调用异常: {e}"], "summary": "", "vision_category": ""}
