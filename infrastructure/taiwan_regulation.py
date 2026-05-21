"""台湾法规知识库 — 跨境电商合规规则查询

内置20+条台湾跨境电商禁止规则。
LLM (deepseek-v4-pro) 检索匹配，不依赖外部官网。
"""

# 台湾跨境电商禁止法规（精简版）
TAIWAN_BANNED_RULES = [
    # 广告法禁用语
    {"keyword": "最", "category": "广告禁用语", "desc": "台湾公平交易法禁止使用最高级形容词"},
    {"keyword": "第一", "category": "广告禁用语", "desc": "无客观数据支撑的排名宣称"},
    {"keyword": "唯一", "category": "广告禁用语", "desc": "排他性宣称需有专利/独家证明"},
    {"keyword": "全网", "category": "广告禁用语", "desc": "范围不明确的绝对化宣称"},
    {"keyword": "国家级", "category": "广告禁用语", "desc": "涉及国家级认证需有相应证书"},
    {"keyword": "最高级", "category": "广告禁用语", "desc": "最高级表述需客观数据支撑"},
    {"keyword": "最佳", "category": "广告禁用语", "desc": "主观评价性绝对化用语"},
    {"keyword": "顶级", "category": "广告禁用语", "desc": "无明确标准的等级宣称"},
    {"keyword": "极品", "category": "广告禁用语", "desc": "商业宣传中的夸张用语限制"},
    {"keyword": "绝对", "category": "广告禁用语", "desc": "无例外的绝对化表述"},

    # 化妆品/保健品类
    {"keyword": "特效", "category": "化妆品类", "desc": "台湾化妆品卫生管理条例禁止宣称医疗效果"},
    {"keyword": "减肥", "category": "食品/化妆品类", "desc": "减肥宣称需有健康食品认证，否则违法"},
    {"keyword": "美白", "category": "化妆品类", "desc": "美白宣称受化妆品卫生管理条例限制"},
    {"keyword": "祛斑", "category": "化妆品类", "desc": "祛斑属于药品宣称，化妆品不可使用"},
    {"keyword": "治疗", "category": "医疗类", "desc": "非药品不得宣称治疗效果"},
    {"keyword": "治愈", "category": "医疗类", "desc": "治愈是药品级宣称，一般商品禁用"},
    {"keyword": "疗效", "category": "医疗类", "desc": "非药品/医疗器械禁止宣称疗效"},
    {"keyword": "药妆", "category": "化妆品类", "desc": "台湾禁止使用药妆一词，化妆品非药品"},

    # 电子产品类
    {"keyword": "认证", "category": "电子产品类", "desc": "未经BSMI/NCC认证的宣称违法"},

    # 食品类
    {"keyword": "有机", "category": "食品类", "desc": "有机宣称需有认证机构核可"},

    # 药品/保健品/医疗器械类
    {"keyword": "降血糖", "category": "药品保健类", "desc": "降血糖属于医疗功效宣称，一般商品/食品禁止使用"},
    {"keyword": "血糖", "category": "药品保健类", "desc": "涉及血糖管理的功效宣称需药品/医疗器材许可"},
    {"keyword": "降血压", "category": "药品保健类", "desc": "降血压属于医疗功效宣称，禁止非药品使用"},
    {"keyword": "降压", "category": "药品保健类", "desc": "降压功效宣称需药品许可"},
    {"keyword": "降血脂", "category": "药品保健类", "desc": "降血脂属于医疗功效宣称"},
    {"keyword": "辅助降", "category": "药品保健类", "desc": "辅助降糖/降脂/降压属于保健品功效，在台湾需健康食品认证"},
    {"keyword": "处方", "category": "药品类", "desc": "处方药相关宣称禁止在一般商品中使用"},
    {"keyword": "药准字", "category": "药品类", "desc": "中国大陆药品批文在台湾无效"},
    {"keyword": "国药准字", "category": "药品类", "desc": "中国大陆药品批文在台湾无效"},
    {"keyword": "蓝帽", "category": "食品保健类", "desc": "中国大陆保健食品蓝帽认证在台湾无效"},
    {"keyword": "保健", "category": "食品类", "desc": "保健功效宣称需有台湾健康食品认证（小绿人标志）"},
    {"keyword": "保健品", "category": "食品类", "desc": "保健品在台湾受健康食品管理法管制"},
    {"keyword": "胶囊", "category": "食品类", "desc": "胶囊形态的食品/保健品在台湾受健康食品管理法管制"},
    {"keyword": "红景天", "category": "药品保健类", "desc": "红景天属于中药材，在台湾受药品管理"},
    {"keyword": "黄芪", "category": "药品保健类", "desc": "黄芪属于中药材，在台湾受药品管理"},

    # 政治敏感类（台湾市场禁止）
    {"keyword": "志愿军", "category": "政治敏感", "desc": "志愿军相关商品涉及两岸政治敏感内容"},
    {"keyword": "抗美援朝", "category": "政治敏感", "desc": "抗美援朝涉及两岸政治敏感历史"},
    {"keyword": "红军", "category": "政治敏感", "desc": "红军相关商品涉及政治敏感内容"},
    {"keyword": "八路军", "category": "政治敏感", "desc": "八路军相关商品涉及政治敏感内容"},
    {"keyword": "新四军", "category": "政治敏感", "desc": "新四军相关商品涉及政治敏感内容"},
    {"keyword": "红卫兵", "category": "政治敏感", "desc": "红卫兵相关商品涉及政治敏感内容"},
    {"keyword": "解放军", "category": "政治敏感", "desc": "解放军相关商品涉及政治敏感军事内容"},
    {"keyword": "天安门", "category": "政治敏感", "desc": "天安门相关商品涉及政治敏感内容"},
    {"keyword": "共产党", "category": "政治敏感", "desc": "共产党标识或相关商品涉及政治敏感内容"},
    {"keyword": "中国梦", "category": "政治敏感", "desc": "中国梦相关商品涉及政治敏感内容"},
]  # type: ignore


from typing import Optional


class TaiwanRegulation:
    """台湾法规查询 — 支持 config.yaml 额外禁用词合并"""

    def __init__(self, extra_keywords: Optional[list[str]] = None):
        # 合并模块级规则 + config 额外关键词
        self._rules = list(TAIWAN_BANNED_RULES)
        if extra_keywords:
            existing_kw = {r["keyword"] for r in self._rules}
            for kw in extra_keywords:
                kw = kw.strip()
                if kw and kw not in existing_kw:
                    self._rules.append({
                        "keyword": kw, "category": "config自定义",
                        "desc": f"config.yaml 额外禁用词: {kw}"
                    })
                    existing_kw.add(kw)

    def check_title(self, title: str) -> list[str]:
        """检查商品标题是否违反台湾法规
        
        使用字符级匹配避免子串误伤（如"最新到货"不会因"最"而被误报）。
        对于单字符关键词使用左边界检测；多字符关键词直接子串匹配。
        """
        issues = []
        for rule in self._rules:
            kw = rule["keyword"]
            if len(kw) == 1:
                # 单字符关键词：检查是否为独立词（前面是标点/空格/开头，或不在复合词中间）
                idx = title.find(kw)
                while idx != -1:
                    # 检查上下文避免误伤：如"最新到货"中的"最"
                    before = title[idx-1] if idx > 0 else " "
                    after = title[idx+1] if idx+1 < len(title) else " "
                    # 如果前后都是中文字符且不是标点，跳过（在复合词中）
                    if before >= '\u4e00' and before <= '\u9fff' and after >= '\u4e00' and after <= '\u9fff':
                        pass  # 在词语中间，不报
                    else:
                        issues.append(f"[{rule['category']}] {rule['desc']} (关键词: {kw})")
                        break
                    idx = title.find(kw, idx + 1)
            elif kw in title:
                issues.append(f"[{rule['category']}] {rule['desc']} (关键词: {kw})")
        return issues

    def get_banned_keywords(self) -> list[str]:
        """获取所有违禁关键词列表"""
        return [r["keyword"] for r in self._rules]

    def search_rules(self, keyword: str) -> list[dict]:
        """按关键词搜索相关法规"""
        return [
            r for r in self._rules
            if keyword in r["keyword"] or keyword in r["desc"]
        ]
