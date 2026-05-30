"""ERP 选择器、文本常量、超时参数 — 集中管理，禁止硬编码

所有文件统一从这里 import 使用。
ERP 使用 TDesign (Vue) 组件库，class 名以 .t-* 开头。
如需适配其他 ERP，只需修改此文件。

使用方式:
    from config.selectors import SEL, TXT, T, wait_visible, calculate_scroll_height
"""

import time as _time


# ═══════════════════════════════════════════════════════════
# CSS 选择器 (SELECTORS) — 集中存放所有 class/attribute 选择器
# ═══════════════════════════════════════════════════════════
class SEL:
    """CSS 选择器 — TDesign 组件库"""
    
    # ── 弹窗 ──
    DIALOG = '[class*="dialog"]'
    DIALOG_VISIBLE = '[class*="dialog"]:not([style*="display: none"])'
    MODAL_VISIBLE = '[class*="modal"]:not([style*="display: none"])'
    DIALOG_ROLE_VISIBLE = '[role="dialog"]:not([style*="display: none"])'
    DIALOG_VISIBLE_ALL = (
        '[class*="dialog"]:not([style*="display: none"]), '
        '[class*="modal"]:not([style*="display: none"]), '
        '[role="dialog"]:not([style*="display: none"])'
    )
    DIALOG_BODY = ".t-dialog__body"
    DIALOG_FOOTER = ".t-dialog__footer"
    DIALOG_CLOSE = ".t-dialog__close"
    DIALOG_CONFIRM = ".t-dialog__confirm"
    
    # ── Tab / 页签 ──
    TAB = '[class*="t-tab"],[class*="radio-button"]'
    TAB_ACTIVE = '[class*="t-tab--active"],[class*="radio-button--active"]'
    
    # ── 表格 / 虚拟滚动 ──
    TABLE_ROW = '[class*="virtual-table-tr"]'
    TABLE_ROW_CHECKBOX = 'input[type="checkbox"]'
    TABLE_HEAD_CHECKBOX = 'thead input[type="checkbox"]'
    SCROLLER = '.vue-recycle-scroller'
    
    # ── 分页 ──
    PAGINATION = '.t-pagination'
    PAGE_NUMBER = '.t-pagination__number'
    
    # ── 按钮 ──
    BUTTON = 'button'
    BUTTON_BASE = '.t-button--variant-base'
    BUTTON_PRIMARY = '.t-button--theme-primary'
    DROPDOWN_ITEM = '[class*="t-dropdown__item"],[class*="dropdown-item"]'
    DROPDOWN_ITEM_TEXT = '.t-dropdown__item-text'
    
    # ── 认领弹窗 ──
    STORE_SECTION = '[class*="select-block-item"]'
    CHECKBOX_GROUP_LABEL = '[class*="checkbox-group"] label, [class*="checkbox"] label'
    STORE_CATEGORY_TAG = '[class*="tag"]:not([class*="platform"]):not([class*="region"])'
    FORM_LABEL = 'label, [class*="label"], [class*="form__label"], span, div'
    FORM_ITEM = '.t-form__item'
    
    # ── 发布页 ──
    STORE_TAG_CHECK = '.t-tag--check'
    STORE_TAG_CHECKED = 't-tag--checked'
    
    # ── 消息 / Toast ──
    SUCCESS_TOAST = '[class*="message--success"], [class*="t-message--success"]'
    
    # ── 其他 ──
    IMG = 'img'
    CHECKBOX = 'input[type="checkbox"]'
    ALL_ELEMENTS = '*'


# ═══════════════════════════════════════════════════════════
# UI 文本 (TEXT) — 集中存放所有自然语言文本
# ERP 升级改了 UI 文案只需改这里
# ═══════════════════════════════════════════════════════════
class TXT:
    """UI 文本 — 所有自然语言匹配文本"""
    
    # ── Tab 名称 ──
    TAB_UNCLAIMED = "未认领"
    TAB_CLAIMED = "已认领"
    TAB_DRAFT = "草稿箱"
    TAB_PUBLISHING = "发布中"
    TAB_PUBLISH_SUCCESS = "发布成功"
    TAB_PUBLISH_FAIL = "发布失败"
    TAB_ALL = "全部"
    TAB_COLLECT_FAIL = "采集失败"
    
    # ── 按钮文本 ──
    BTN_CLAIM = "认领"
    BTN_DELETE = "删除"
    BTN_CONFIRM = "确认"
    BTN_SUBMIT = "确定"  # 有些弹窗用"确定"
    BTN_SAVE = "保存"
    BTN_PUBLISH = "产品发布"
    BTN_PUBLISH_NOW = "立即发布"
    BTN_QUERY = "查询"
    BTN_SKIP = "跳过"
    BTN_CANCEL = "取消"
    BTN_CLOSE = ""  # 关闭按钮通常无文本，用 class 选择器
    
    # ── 表单 label ──
    LABEL_STORE = "店铺"
    LABEL_SELECT_STORE = "选择店铺"
    LABEL_ALL = "全部"
    LABEL_SHOPEE = "Shopee"
    LABEL_TAIWAN = "台湾"
    
    # ── 弹窗文本 ──
    DIALOG_SKIP_UNCATEGORIZED = "跳过未设置类目产品并继续发布"
    DIALOG_PUBLISH_SUCCESS = "发布成功"
    
    # ── 正则匹配（用于 JS evaluate 中匹配中文，避免编码问题） ──
    # 直接用 unicode 转义：\u672a\u8ba4\u9886 = 未认领
    # \u8349\u7a3f\u7bb1 = 草稿箱
    # \u5220\u9664 = 删除
    # \u786e\u8ba4 = 确认
    # \u786e\u5b9a = 确定
    # \u8ba4\u9886 = 认领
    # \u4fdd\u5b58 = 保存
    # \u4ea7\u54c1\u53d1\u5e03 = 产品发布
    # \u7acb\u5373\u53d1\u5e03 = 立即发布
    # \u67e5\u8be2 = 查询
    # \u8df3\u8fc7 = 跳过
    
    # ERP ID 匹配正则
    ERP_ID_PATTERN = r'货源ID[：:]\s*(\d+)'
    MASTER_ID_PATTERN = r'主货号[：:]\s*(\d+)'
    PRICE_PATTERN = r'CNY\s*(\S+?)(?:\s|$|\d+未)'


# ═══════════════════════════════════════════════════════════
# 超时 / 延迟参数 (TIMEOUTS)
# ═══════════════════════════════════════════════════════════
class T:
    """超时 / 延迟时间（毫秒）"""
    
    # ── 导航 ──
    NAVIGATION = 60_000          # page.goto 最大等待
    NETWORK_IDLE = 30_000        # wait_for_load_state("networkidle")
    
    # ── 弹窗 ──
    DIALOG_APPEAR = 10_000       # 认领弹窗等待
    DIALOG_CONFIRM = 5_000       # 确认弹窗等待
    DIALOG_CLOSE = 1_000         # 关弹窗后等待
    
    # ── 元素可见 ──
    ELEMENT_VISIBLE = 3_000      # is_visible 超时
    ELEMENT_VANISH = 3_000       # 等元素消失
    
    # ── 页面刷新 ──
    PAGE_REFRESH = 2_000         # 翻页/刷新后等待
    AFTER_CLICK = 500            # 点击后的短等待
    AFTER_SCROLL = 300           # 滚动后的等待
    
    # ── 删除 ──
    DELETE_CONFIRM = 3_000       # 删除确认后等待
    DELETE_RESULT = 2_000        # 删除结果弹窗关闭后等待
    
    # ── 发布 ──
    PUBLISH_INITIAL = 5_000      # 发布页初始加载
    PUBLISH_CLICK = 1_500        # 点击发布后等待
    PUBLISH_SAVE = 2_000         # 保存后等待
    
    # ── 审查 ──
    REVIEW_INITIAL = 3_000       # 审查后等待
    REVIEW_RETRY = 3_000         # 审查重试间隔
    
    # ── 虚拟滚动 ──
    SCROLL_RENDER = 1_000        # 扩高后等待渲染
    SCROLL_STEP_WAIT = 500       # 每步滚动后等待
    SCROLL_FAST = 150            # 快速滚动
    SCROLL_RECOVER = 300         # 恢复页面后等待
    
    # ── 通用 ──
    SHORT_SLEEP = 300            # 300ms
    ONE_SECOND = 1_000
    TWO_SECONDS = 2_000
    THREE_SECONDS = 3_000
    FIVE_SECONDS = 5_000
    HALF_SECOND = 500
    
    # ── CDP ──
    CDP_CONNECT = 5_000          # CDP 连接等待
    
    # ── 重试 ──
    RETRY_DELAY = 3_000          # 重试间隔


# ═══════════════════════════════════════════════════════════
# 数量 / 尺寸常量 (CONSTANTS)
# ═══════════════════════════════════════════════════════════
class C:
    """数量 / 尺寸常量"""
    
    PAGE_SIZE = 20                              # ERP 每页固定 20 条
    EXPANDED_HEIGHT_PER_PAGE = 3000             # 每页扩高 3000px
    MAX_VIRTUAL_HEIGHT = 80_000                 # 虚拟滚动最大扩高
    SCROLL_STEP = 200                           # 滚动步长 px
    SCROLL_FAST_STEP = 150                      # 快速滚动步长 px
    SCROLL_INTERNAL_STEP = 80                   # 内部滚动步长 px
    MAX_SCROLL_STEPS = 60                       # 最大滚动次数
    MAX_STABLE_ROUNDS = 15                      # 连续无新增退出
    SCROLL_DELETE_STEP = 200                    # 删除循环滚动步长 px
    
    MAX_RETRIES = 3                             # 重试次数
    MAX_CLAIM_RETRIES = 5                       # 认领弹窗重试
    MAX_NAVIGATION_RETRIES = 3                  # 导航重试
    CLAIM_REPLACE_OFFSET = 10                   # claim-and-replace 循环偏移量
    DELETE_REPLACE_OFFSET = 5                   # 删除循环偏移量
    PUBLISH_REPLACE_OFFSET = 10                 # 发布循环偏移量
    
    DIALOG_POLL_MAX = 20                        # 弹窗轮询最大次数
    DIALOG_POLL_INTERVAL = 0.5                  # 弹窗轮询间隔（秒）
    DIALOG_SKIP_POLL_MAX = 10                   # 跳过弹窗后轮询最大次数
    DIALOG_SKIP_POLL_INTERVAL = 0.5             # 跳过弹窗后轮询间隔（秒）
    
    ALIGN_CHECK_COUNT_MAX = 5                   # 连续无新增检测次数


# ═══════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════

def calculate_scroll_height(tab_count: int) -> int:
    """根据 tab 商品数量动态计算页面扩高值
    
    Args:
        tab_count: 未认领/草稿箱商品数
        
    Returns:
        扩高 px 值（介于 3000 和 MAX_VIRTUAL_HEIGHT 之间）
    """
    return min(
        max(tab_count * C.EXPANDED_HEIGHT_PER_PAGE, 3000),
        C.MAX_VIRTUAL_HEIGHT
    )


def wait_visible(page, selector: str, timeout_ms: int = T.ELEMENT_VISIBLE,
                 raise_error: bool = False) -> bool:
    """等待选择器可见的封装（替代固定 time.sleep）
    
    Args:
        page: Playwright page
        selector: CSS 选择器
        timeout_ms: 超时毫秒
        raise_error: 超时后是否抛异常
        
    Returns:
        bool 是否可见
    """
    try:
        page.wait_for_selector(selector, timeout=timeout_ms)
        return True
    except Exception:
        if raise_error:
            raise
        return False


def wait_dialog(page, timeout_ms: int = T.DIALOG_APPEAR) -> bool:
    """等待弹窗出现（任意一种弹窗选择器）
    
    Returns:
        bool 是否出现
    """
    return wait_visible(page, SEL.DIALOG_VISIBLE_ALL, timeout_ms)


def close_dialogs(page):
    """关所有可见弹窗"""
    page.evaluate(f"""() => {{
        const closes = document.querySelectorAll('.t-dialog__close, [class*="dialog"] [class*="close"]');
        for (const c of closes) {{
            if (c.offsetParent !== null && typeof c.click === 'function') c.click();
        }}
    }}""")


def hide_dialogs(page):
    """隐藏所有弹窗（用 display:none 方案兜底）"""
    page.evaluate(f"""() => {{
        document.querySelectorAll('{SEL.DIALOG}').forEach(d => {{
            d.style.display = 'none';
        }});
    }}""")


def switch_tab(page, tab_text: str):
    """切换到指定 tab
    
    Args:
        page: Playwright page
        tab_text: tab 名称（如"未认领""草稿箱"）
    """
    page.evaluate(f"""() => {{
        const tabs = document.querySelectorAll('{SEL.TAB}');
        for (const t of tabs) {{
            if (t.textContent.includes('{tab_text}')) {{
                t.click(); return;
            }}
        }}
    }}""")


def expand_and_scroll(page, height: int = None, tab_count: int = None):
    """扩高页面 + 全量滚动，触发虚拟滚动渲染全部行
    
    Args:
        page: Playwright page
        height: 扩高 px，不传则用 tab_count 动态计算
        tab_count: 商品数，用于动态计算高度
    """
    if height is None and tab_count is not None:
        height = calculate_scroll_height(tab_count)
    if height is None:
        height = C.EXPANDED_HEIGHT_PER_PAGE  # 默认
    
    page.evaluate(f"""(h) => {{
        document.body.style.minHeight = h + "px";
        document.documentElement.style.minHeight = h + "px";
        window.scrollTo(0, 0);
    }}""", height)
    _time.sleep(T.SCROLL_RENDER / 1000)
    
    step = C.SCROLL_STEP
    for y in range(0, height, step):
        page.evaluate(f"window.scrollTo(0, {y})")
    page.evaluate("window.scrollTo(0, 0)")
    _time.sleep(T.SCROLL_RENDER / 1000)


def recover_page(page):
    """恢复页面扩高和滚动位置"""
    page.evaluate("""() => {
        window.scrollTo(0, 0);
        document.body.style.minHeight = "";
        document.documentElement.style.minHeight = "";
    }""")
    _time.sleep(T.SCROLL_RECOVER / 1000)


def sleep(ms: int):
    """替代直接 time.sleep 的统一休眠函数
    
    Args:
        ms: 毫秒
    """
    _time.sleep(ms / 1000)
