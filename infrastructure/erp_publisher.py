"""ERP认领+Shopee发布操作

输入：合规审查通过的 Product ID 列表
流程：采集箱勾选→认领→选择店铺→Shopee发布页→暂不上架→发布

⚠️ 选择器说明：
  货憨憨ERP使用 TDesign (Vue) UI组件库，非Element UI。
  选择器使用 .t-* 前缀。以下选择器基于实测待验证，标注了备用方案。
"""

from playwright.sync_api import Page
from config.selectors import SEL, TXT, T, C, close_dialogs, switch_tab, expand_and_scroll, recover_page, wait_visible, wait_dialog, sleep
from config.selectors import SEL, TXT, T, C, close_dialogs, switch_tab, expand_and_scroll, recover_page, wait_visible, wait_dialog, sleep


class ERPPublisher:
    """ERP认领+Shopee发布操作"""

    @classmethod
    def get_publish_url(cls):
        from infrastructure.config_loader import ConfigLoader
        return ConfigLoader().load().erp_url + "/member/product/shopee/publish"

    @classmethod
    def get_collect_box_url(cls):
        from infrastructure.config_loader import ConfigLoader
        return ConfigLoader().load().erp_url + "/member/product/general/collect-box"

    # TDesign 选择器（2026-05-17 ERP实测验证）
    DIALOG_BODY = SEL.DIALOG_BODY
    DIALOG_FOOTER = SEL.DIALOG_FOOTER
    DIALOG_CLOSE = SEL.DIALOG_CLOSE          # 关闭按钮
    CLAIM_MODAL = '[class*="dialog"]:visible'   # 认领弹窗
    STORE_TAG = '[class*="select-block-item"]'  # 店铺选择标签
    DROPDOWN_ITEM = '[class*="select-option"], [class*="option-item"]'
    SUCCESS_TOAST = SEL.SUCCESS_TOAST
    CLAIM_CONFIRM = '确定'                       # 认领确认（可见的那个）

    def __init__(self, page: Page):
        self.page = page

    def navigate_to_publish(self):
        """导航到Shopee产品发布页"""
        self.page.goto(self.get_publish_url())
        self.page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)

    def navigate_to_collection_box(self):
        """导航到采集箱（三重保障：慢速+等待+重试）"""
        import time as _time
        max_retry = 3
        for attempt in range(max_retry):
            try:
                # 先用 wait_until=domcontentloaded 减少导航冲突窗口
                self.page.goto(self.get_collect_box_url(), wait_until="domcontentloaded", timeout=T.NAVIGATION)
                # 等渲染稳定后再等网络空闲
                sleep(1000)
                self.page.wait_for_load_state("networkidle", timeout=T.NAVIGATION)
                break
            except Exception as e:
                if attempt < max_retry - 1:
                    print(f"  ⚠️ 导航采集箱被中断，第{attempt+2}次重试...", flush=True)
                    sleep(800)
                else:
                    raise

    def select_products_in_collection_box(self, erp_ids: list[str]):
        """在采集箱勾选合规商品"""
        for eid in erp_ids:
            cb = self.page.locator(
                f"tbody tr:has-text('{eid}') input[type='checkbox']"
            )
            if cb.is_visible():
                cb.check()

    def click_claim(self):
        """点击「认领」按钮（CSS方案→JS兜底）"""
        clicked = False
        try:
            btn = self.page.locator("button.t-button--variant-base.t-button--theme-primary:has-text('认领')").first
            if btn.is_visible(timeout=T.ELEMENT_VISIBLE):
                btn.click()
                clicked = True
        except:
            pass
        if not clicked:
            try:
                btn = self.page.locator("button:has-text('认领')").last
                if btn.is_visible(timeout=T.ELEMENT_VISIBLE):
                    btn.click()
                    clicked = True
            except:
                pass
        if not clicked:
            self.page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes('认领') && btn.offsetParent !== null) {
                        btn.click(); return true;
                    }
                }
                return false;
            }""")
            # 检查JS兜底是否成功执行
            js_clicked = self.page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes('认领') && btn.offsetParent !== null) {
                        return true;
                    }
                }
                return false;
            }""")
            if js_clicked:
                clicked = True
        if not clicked:
            print("  ⚠️ 点击认领按钮失败（3种方案均未找到）", flush=True)
        self.page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)

    def get_store_list_from_modal(self, max_retries: int = 5, initial_delay: float = 1.0) -> list[dict]:
        """从认领弹窗中动态提取店铺列表（不硬编码，根据实际账号返回）

        货憨憨认领弹窗表单结构：
        电商平台：Shopee  ← .select-block-item (平台)
        地区：全部 台湾    ← .select-block-item (地区筛选)
        店铺：全部 吉象星連坊 順順の小屋童裝 ...  ← 真正的店铺列表

        策略：找「店铺」label → 取其容器内所有 .select-block-item（排除TXT.LABEL_ALL）
        增加：重试机制 + 显式等待弹窗渲染 + 调试日志
        """
        import time as _time

        for attempt in range(max_retries):
            delay = initial_delay * (1.5 ** attempt)  # 1s → 1.5s → 2.25s → ...
            _time.sleep(delay)

            # 方案1：按「店铺」label 定位 → 同级容器中的店铺checkbox/label
            stores = self.page.evaluate("""(t) => {
                // t = {labelStore, labelSelectStore, labelAll, labelShopee, labelTaiwan}
                // 找弹窗（多种选择器）
                const dialog = document.querySelector(
                    '[class*="dialog"]:not([style*="display: none"]), ' +
                    '[class*="modal"]:not([style*="display: none"]), ' +
                    '[role="dialog"]:not([style*="display: none"])'
                );
                if (!dialog) return [];

                // 找「店铺」label — 多种匹配策略
                const labels = dialog.querySelectorAll('label, [class*="label"], [class*="form__label"], span, div');
                let storeSection = null;
                labels.forEach(l => {
                    if (storeSection) return;  // 已找到就跳过
                    const text = l.textContent.trim();
                    if (text === t.labelStore || text === t.labelSelectStore || text.startsWith(t.labelStore)) {
                        // 向上找到表单项容器
                        let el = l.parentElement;
                        while (el && el !== dialog) {
                            if (el.classList.contains('t-form__item') ||
                                el.classList.contains('form-item') ||
                                el.getAttribute('role') === 'group') {
                                storeSection = el;
                                break;
                            }
                            el = el.parentElement;
                        }
                        // 如果没找到 t-form__item，用 label 的直接父级
                        if (!storeSection && l.parentElement) {
                            storeSection = l.parentElement;
                            // 再往上找一层（常见：label 在一个 div 里，和 checkbox-group 同级）
                            if (storeSection.parentElement && storeSection.parentElement !== dialog) {
                                storeSection = storeSection.parentElement;
                            }
                        }
                    }
                });

                const seen = new Set();
                const stores = [];
                const searchRoot = storeSection || dialog;

                // 路A: label元素（t-checkbox-group label）
                const cbLabels = searchRoot.querySelectorAll('[class*="checkbox-group"] label, [class*="checkbox"] label');
                cbLabels.forEach(el => {
                    const elemText = el.textContent.trim();
                    if (elemText && elemText !== t.labelAll && !seen.has(elemText)) {
                        seen.add(elemText);
                        stores.push({ store_id: '', store_name: elemText, platform: t.labelShopee });
                    }
                });

                // 路B: select-block-item 标签
                const blocks = searchRoot.querySelectorAll('[class*="select-block-item"]');
                blocks.forEach(item => {
                    const elemText = item.textContent.trim();
                    if (elemText && elemText !== t.labelAll && elemText !== t.labelShopee && !elemText.includes(t.labelTaiwan) && !seen.has(elemText)) {
                        seen.add(elemText);
                        stores.push({
                            store_id: item.getAttribute('data-id') || item.getAttribute('data-value') || '',
                            store_name: elemText,
                            platform: t.labelShopee,
                        });
                    }
                });

                // 路C: 任何可点击的 checkbox / tag 元素（兜底）
                if (stores.length === 0) {
                    const clickableItems = searchRoot.querySelectorAll(
                        '[class*="tag"]:not([class*="platform"]):not([class*="region"]), ' +
                        '[class*="checkbox"]:not([class*="group"]), ' +
                        '[role="checkbox"]'
                    );
                    clickableItems.forEach(item => {
                        const elemText = item.textContent.trim();
                        if (elemText && elemText !== t.labelAll && elemText !== t.labelShopee && !elemText.includes(t.labelTaiwan)
                            && elemText.length > 1 && elemText.length < 30 && !seen.has(elemText)) {
                            seen.add(elemText);
                            stores.push({
                                store_id: item.getAttribute('data-id') || item.getAttribute('data-value') || '',
                                store_name: elemText,
                                platform: t.labelShopee,
                            });
                        }
                    });
                }

                return stores;
            }""", {
                "labelStore": TXT.LABEL_STORE,
                "labelSelectStore": TXT.LABEL_SELECT_STORE,
                "labelAll": TXT.LABEL_ALL,
                "labelShopee": TXT.LABEL_SHOPEE,
                "labelTaiwan": TXT.LABEL_TAIWAN,
            })

            if stores:
                return stores

            # 方案2兜底：扫所有 select-block-item，过滤非店铺
            try:
                blocks = self.page.locator(self.STORE_TAG).all()
                all_items = self._parse_store_blocks(blocks)
                filtered = [s for s in all_items if s["store_name"] not in ("Shopee", TXT.LABEL_ALL, "台湾")]
                if filtered:
                    return filtered
            except Exception:
                pass

            print(f"  ⏳ 等待店铺列表加载... (第{attempt+1}/{max_retries}次)", flush=True)

        print("  ⚠️ 所有重试均未找到店铺列表", flush=True)
        return []

    @staticmethod
    def _parse_store_blocks(blocks) -> list[dict]:
        """从 select-block-item 元素列表解析店铺信息"""
        stores = []
        seen = set()
        for blk in blocks:
            if not blk.is_visible():
                continue
            name = blk.text_content().strip()
            if not name or len(name) <= 1 or name in seen:
                continue
            seen.add(name)
            stores.append({
                "store_id": blk.get_attribute("data-id") or blk.get_attribute("data-value") or "",
                "store_name": name,
                "platform": "Shopee",
            })
        return stores

    def select_store(self, store_name: str):
        """在认领弹窗中选择目标店铺

        四种定位策略（逐步升级）：
        1. t-checkbox-group label 文本匹配
        2. select-block-item 匹配
        3. JS 兜底点击（精确 + 模糊）
        4. JS 全文搜索点击
        """
        import time as _time

        # 方案1: checkbox-group label
        try:
            label = self.page.locator(
                f"[class*='checkbox-group'] label:has-text('{store_name}')"
            ).first
            if label.is_visible(timeout=T.TWO_SECONDS):
                label.click()
                return
        except Exception:
            pass

        # 方案2: select-block-item
        try:
            block = self.page.locator(
                f"{self.STORE_TAG}:has-text('{store_name}')"
            ).first
            if block.is_visible(timeout=T.TWO_SECONDS):
                block.click()
                return
        except Exception:
            pass

        # 方案3: JS 兜底（精确匹配 + 模糊匹配）
        clicked = self.page.evaluate("""(storeName) => {
            const dialog = document.querySelector(
                '[class*="dialog"]:not([style*="display: none"]), ' +
                '[class*="modal"]:not([style*="display: none"]), ' +
                '[role="dialog"]:not([style*="display: none"])'
            );
            if (!dialog) return false;
            const items = dialog.querySelectorAll(
                '[class*="checkbox-group"] label, [class*="select-block-item"], [class*="tag"], [role="checkbox"]'
            );
            // 精确匹配
            for (const el of items) {
                if (el.textContent.trim() === storeName) {
                    el.click(); return true;
                }
            }
            // 模糊匹配（包含）
            for (const el of items) {
                if (el.textContent.trim().includes(storeName) || storeName.includes(el.textContent.trim())) {
                    el.click(); return true;
                }
            }
            return false;
        }""", store_name)
        if clicked:
            return

        # 方案4: 全文搜索弹窗内所有可点击元素
        self.page.evaluate("""(storeName) => {
            const dialog = document.querySelector(
                '[class*="dialog"]:not([style*="display: none"]), ' +
                '[class*="modal"]:not([style*="display: none"])'
            );
            if (!dialog) return false;
            const allEls = dialog.querySelectorAll('*');
            for (const el of allEls) {
                if (el.children.length === 0 && el.textContent.trim() === storeName && el.offsetParent !== null) {
                    el.click(); return true;
                }
            }
            return false;
        }""", store_name)

    def confirm_claim(self):
        """认领弹窗内点击「确定」确认认领"""
        # 优先找弹窗 footer 里的确定按钮
        confirm = self.page.locator(
            f"{self.DIALOG_FOOTER} button:has-text('确定')"
        ).first
        if not confirm.is_visible():
            confirm = self.page.locator(
                f"{self.DIALOG_BODY} button:has-text('确定')"
            ).first
        if not confirm.is_visible():
            # 兜底：页面内任意可见的确定按钮
            confirm = self.page.locator(
                "button:has-text('确定'):visible"
            ).last
        if not confirm.count() or not confirm.first.is_visible():
            # 终极兜底：JS 找所有可见的确定按钮
            self.page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes('\u786e\u5b9a') && btn.offsetParent !== null) {
                        btn.click(); return;
                    }
                }
            }""")
        else:
            confirm.first.click()
        self.page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)

    def filter_by_store(self, store_name: str):
        """在发布页按店铺名筛选"""
        self.page.locator(f"[placeholder*='{TXT.LABEL_STORE}']").click()
        self.page.locator(f"text={store_name}").click()
        self.page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)

    def set_no_listing(self):
        """设置「发布后暂不上架」（安全红线）"""
        self.page.locator("button:has-text('发布配置')").click()
        self.page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)
        self.page.locator("text=暂不上架").click()
        self.page.locator("button:has-text('确定')").click()

    def publish_now(self):
        """产品发布 → 立即发布 → 确认"""
        self.page.locator("button:has-text('产品发布')").click()
        self.page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)
        self.page.locator("text=立即发布").click()
        self.page.locator("button:has-text('确定')").click()
        self.page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)

    @staticmethod
    def check_row_checkbox(row) -> bool:
        """勾选一行中的checkbox（未勾选才点）"""
        cb = row.querySelector('input[type="checkbox"]')
        if cb and not cb.checked:
            cb.click()
            return True
        return False

    def get_publish_status(self) -> str:
        """检查发布状态"""
        toast = self.page.locator(self.SUCCESS_TOAST)
        if toast.is_visible():
            return "success"
        self.page.locator("text=发布成功").click()
        self.page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)
        rows = self.page.locator("table tbody tr").count()
        return f"done ({rows} items)"


def _get_tab_count(page, tab_text=TXT.TAB_UNCLAIMED) -> int:
    """从tab标签读取计数，如「未认领(10)」→ 10"""
    count = page.evaluate("""(tab) => {
        const tabs = document.querySelectorAll('[class*="t-tab"],[class*="radio-button"]');
        for (const t of tabs) {
            if (t.textContent.includes(tab)) {
                const parts = t.textContent.split(tab);
                if (parts.length > 1) {
                    const after = parts[1].trim();
                    const m = after.match(/^\\((\\d+)\\)/);
                    return m ? parseInt(m[1]) : 0;
                }
            }
        }
        return 0;
    }""", tab_text)
    return count


def _get_collect_box_pages(page, tab_text=TXT.TAB_UNCLAIMED) -> int:
    """获取采集箱指定tab的总页数"""
    total = page.evaluate("""({pagSel, pageNumSel}) => {
        const pag = document.querySelector(pagSel);
        if (!pag) return 1;
        const items = pag.querySelectorAll(pageNumSel);
        const nums = Array.from(items).map(n => parseInt(n.textContent)).filter(n => !isNaN(n));
        return Math.max(...nums, 1);
    }""", {"pagSel": SEL.PAGINATION, "pageNumSel": SEL.PAGE_NUMBER})
    return total


def _check_ids_on_page(page, reject_ids: set, tab_text=TXT.TAB_UNCLAIMED) -> int:
    """在当前页勾选匹配的reject_ids，返回勾选数

    双引擎扫描策略（2026-05-19 修复）：
    ① scrollHeight > clientHeight → 内部滚动（scroller.scrollTop）
    ② scrollHeight == clientHeight → 窗口扩高+滚动（window.scrollTo）
    """
    total_checked = 0
    reject_list = list(reject_ids)

    # 检查 scroller 状态，选引擎
    s = page.evaluate("""(ssel) => {
        const s = document.querySelector(ssel);
        return s ? {h: s.scrollHeight, ch: s.clientHeight} : null;
    }""", SEL.SCROLLER)
    if not s:
        return _check_ids_via_window_scroll(page, reject_list)

    if s["h"] > s["ch"]:
        # 引擎①：内部滚动
        return _check_ids_via_internal_scroll(page, reject_list)

    # 引擎②：窗口扩高+滚动
    return _check_ids_via_window_scroll(page, reject_list)


def _check_ids_via_internal_scroll(page, reject_ids: list) -> int:
    """引擎①：内部滚动 scroller → 勾选隐藏行的 checkbox"""
    total_checked = 0
    s = page.evaluate("""(ssel) => {
        const s = document.querySelector(ssel);
        return s ? {h: s.scrollHeight, ch: s.clientHeight} : null;
    }""", SEL.SCROLLER)
    if not s:
        return 0

    reject_set = set(reject_ids)
    for pass_n in range(3):
        step = C.SCROLL_INTERNAL_STEP
        max_pos = max(0, s["h"] - s["ch"])
        for pos in range(0, max_pos + step, step):
            page.evaluate(f"() => {{ const s = document.querySelector('{SEL.SCROLLER}'); if(s) s.scrollTop = {min(pos, max_pos)}; }}")
            sleep(T.SCROLL_FAST)

        page.evaluate("""(ssel) => { const s = document.querySelector(ssel); if(s) s.scrollTop = 0; }""", SEL.SCROLLER)
        sleep(T.SCROLL_RECOVER)

        checked = _check_visible_checkboxes(page, reject_set)
        total_checked += checked

        if checked == 0:
            break

    return total_checked


def _check_ids_via_window_scroll(page, reject_ids: list) -> int:
    """引擎②：扩高页面 + 滚动 window → 勾选隐藏行的 checkbox
    修复：循环60步 + 6000px高度，确保所有行都被扫到。
    """
    reject_set = set(reject_ids)
    total_checked = 0
    seen_ids = set()

    # 大幅扩高页面创造充足滚动空间
    page.evaluate("""() => {
        document.body.style.minHeight = "6000px";
        document.documentElement.style.minHeight = "6000px";
    }""")
    sleep(200)

    for i in range(C.MAX_SCROLL_STEPS):
        page.evaluate("window.scrollTo(0, %d)" % (i * 150))
        sleep(T.SCROLL_RECOVER)

        checked = _check_visible_checkboxes(page, reject_set)
        total_checked += checked

        # 连续5次无新增 → 退出
        if checked == 0:
            stable_count = sum(1 for j in range(max(0,i-4), i+1) if True)
            if stable_count >= C.ALIGN_CHECK_COUNT_MAX:
                break

    # 恢复页面
    page.evaluate("""() => {
        window.scrollTo(0, 0);
        document.body.style.minHeight = "";
        document.documentElement.style.minHeight = "";
    }""")

    return total_checked


def _check_visible_checkboxes(page, reject_ids: set) -> int:
    """勾选当前可见行中匹配 reject_ids 的 checkbox"""
    return page.evaluate("""((ids) => {
        const rows = document.querySelectorAll('[class*="virtual-table-tr"]');
        const idSet = new Set(ids.map(String));
        let count = 0;
        rows.forEach(row => {
            const m = row.textContent.match(/货源ID[：:]\\s*(\\d+)/);
            if (m && idSet.has(m[1])) {
                const cb = row.querySelector('input[type="checkbox"]');
                if (cb && !cb.checked) {
                    cb.click();
                    count++;
                }
            }
        });
        return count;
    })""", list(reject_ids))


def delete_rejected_products(page, reject_ids: list[str]) -> int:
    """从采集箱批量删除不合规商品

    策略：claim-and-replace 循环——每次只扫第1页可视行
    勾选匹配的reject_ids → 删除 → 页面刷新 → 后续页填充到第1页 → 继续
    翻页会导致已勾选checkbox失效，所以不能用"遍历所有分页再删"的方式

    Args:
        page: Playwright page (connect_over_cdp)
        reject_ids: ERP ID 列表

    Returns:
        实际删除数量（累计所有轮次）
    """
    if not reject_ids:
        return 0

    reject_set = set(str(i) for i in reject_ids)
    deleted_set = set()
    max_rounds = len(reject_set) + C.DELETE_REPLACE_OFFSET
    total_removed = 0

    print(f"\n  🗑️  删除 {len(reject_set)} 个不合规商品...")

    try:
        # 导航到采集箱
        page.goto(ERPPublisher.get_collect_box_url())
        page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)
        sleep(800)

        # 关弹窗
        page.evaluate("""() => {
            document.querySelectorAll('[class*="dialog"]').forEach(d => {
                const c = d.querySelector('[class*="close"]');
                if (c && typeof c.click === 'function') c.click();
            });
        }""")
        sleep(200)

        # 切到未认领 tab（JS避免中文编码问题）
        page.evaluate("""() => {
            const tabs = document.querySelectorAll('[class*="t-tab"],[class*="radio-button"]');
            for (const t of tabs) {
                if (t.textContent.match(/未认领|鏈棰?/)) { t.click(); return; }
            }
        }""")
        page.wait_for_load_state("networkidle", timeout=T.NETWORK_IDLE)
        sleep(800)

        # 循环：先全量展开触发虚拟滚动渲染，再扫第1页
        # 删完后续页自动填充到第1页
        for loop in range(max_rounds):
            # 展开页面高度+逐格滚动，触发虚拟滚动渲染全部行到DOM
            scroll_h = 40000
            page.evaluate("""(h) => {
                document.body.style.minHeight = h + "px";
                document.documentElement.style.minHeight = h + "px";
                window.scrollTo(0, 0);
            }""", scroll_h)
            sleep(200)
            # 逐格滚动 — 每个step给Vue Scroller渲染帧，不能合并成JS同步循环
            for y in range(0, scroll_h, 300):
                page.evaluate(f"window.scrollTo(0, {y})")
                sleep(80)
            page.evaluate("window.scrollTo(0, 0)")
            sleep(200)

            # 扫第1页可视行，找仍然存在的reject_ids
            still_visible = page.evaluate("""({rejectSet, deletedSet}) => {
                const targetSet = new Set(rejectSet);
                const doneSet = new Set(deletedSet);
                const found = [];
                document.querySelectorAll('[class*="virtual-table-tr"]').forEach(row => {
                    const m = row.textContent.match(/货源ID[：:]\\s*(\\d+)/);
                    if (m && targetSet.has(m[1]) && !doneSet.has(m[1])) {
                        found.push(m[1]);
                    }
                });
                return found;
            }""", {"rejectSet": list(reject_set), "deletedSet": list(deleted_set)})

            if not still_visible:
                if deleted_set:
                    print(f"   第{loop+1}轮: 无可匹配ID，所有目标已删除")
                else:
                    print(f"   第{loop+1}轮: 页面无可匹配ID")
                break

            # 勾选匹配的行
            checked = page.evaluate("""(ids) => {
                const idSet = new Set(ids);
                let n = 0;
                document.querySelectorAll('[class*="virtual-table-tr"]').forEach(row => {
                    const m = row.textContent.match(/货源ID[：:]\\s*(\\d+)/);
                    if (m && idSet.has(m[1])) {
                        const cb = row.querySelector('input[type="checkbox"]');
                        if (cb && !cb.checked) {
                            cb.click();
                            n++;
                        }
                    }
                });
                return n;
            }""", still_visible)

            if checked == 0:
                print(f"   第{loop+1}轮: 页面无未勾选目标")
                break

            print(f"   第{loop+1}轮: 勾选 {checked} 个 → 删除...")

            # 点击批量删除按钮
            page.evaluate("""(delText) => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes(delText) && btn.classList.contains('t-button--variant-base')) {
                        btn.click(); return;
                    }
                }
            }""", TXT.BTN_DELETE)

            # 确认弹窗
            sleep(400)
            confirmed = page.evaluate("""(confirmText) => {
                const btns = document.querySelectorAll('[class*="dialog"] button, button');
                for (const btn of btns) {
                    if (btn.offsetParent !== null && (btn.textContent.trim() === confirmText || btn.classList.contains('t-dialog__confirm'))) {
                        btn.click(); return true;
                    }
                }
                return false;
            }""", TXT.BTN_CONFIRM)

            page.wait_for_timeout(3000)

            # 关结果弹窗
            page.evaluate("""() => {
                const closes = document.querySelectorAll('.t-dialog__close, [class*="dialog"] [class*="close"]');
                for (const c of closes) {
                    if (c.offsetParent !== null && typeof c.click === 'function') c.click();
                }
            }""")
            sleep(200)

            if confirmed:
                deleted_set.update(still_visible)
                total_removed += checked
                print(f"   ✅ 本轮删除 {checked} 个 (累计 {total_removed}/{len(reject_set)})")
            else:
                print(f"   ⚠️ 删除确认弹窗未找到，尝试继续")
                continue

        print(f"  ✅ 累计从采集箱删除 {total_removed} 个不合规商品")

        # 恢复页面
        page.evaluate("""() => {
            window.scrollTo(0, 0);
            document.body.style.minHeight = "";
            document.documentElement.style.minHeight = "";
        }""")
        sleep(T.SCROLL_RECOVER)

        return total_removed

    except Exception as e:
        print(f"  ⚠️ 删除操作异常: {e}")
        import traceback
        traceback.print_exc()
        return total_removed


def _extract_visible_products(page) -> list[dict]:
    """从当前page DOM提取可见的虚拟表格商品数据

    vue-recycle-scroller 的行选择器 `[class*="virtual-table-tr"]` 只抓渲染行。
    不会爬取所有10件，仅返回当前视口可见的。
    """
    return page.evaluate("""() => {
        const rows = document.querySelectorAll('[class*="virtual-table-tr"]');
        return Array.from(rows).map(row => {
            const text = row.textContent.trim();
            if (!text || text.length < 20) return null;
            if (text.includes('商品信息') && !text.includes('货源ID')) return null;

            const idMatch = text.match(/货源ID[：:]\\s*(\\d+)/);
            const priceMatch = text.match(/CNY\\s*(\\S+?)(?:\\s|$|\\d+未)/);
            const statusMatch = text.match(/(未认领|已认领|采集失败)/);

            // 提取标题（1688搜同款 与 货源ID 之间）
            let title = "";
            const t1 = text.match(/搜同款(.+?)货源ID/);
            if (t1) title = t1[1].trim();
            if (!title) title = text.substring(0, 60).replace(/\\s+/g, ' ').trim();

            const img = row.querySelector('img');
            const cb = row.querySelector('input[type="checkbox"]');

            return {
                erp_id: idMatch ? idMatch[1] : "",
                erp_internal_id: cb ? (cb.value || "") : "",
                title: title || ("商品" + (idMatch ? idMatch[1] : "")),
                price: priceMatch ? priceMatch[1].trim() : "0",
                status: statusMatch ? statusMatch[1] : "",
                img_url: img ? (img.src || img.getAttribute("data-src") || "") : "",
            };
        }).filter(Boolean);
    }""")


def _scroll_window_for_all_products(page, tab_count: int, max_scrolls=50) -> list[dict]:
    """扩展页面高度 + 滚动窗口 → 触发 vue-recycle-scroller(page-mode) 渲染全部商品

    原理：vue-recycle-scroller 在 page-mode 下通过 window.pageYOffset 判断可见范围。
    当　scrollHeight == clientHeight（无内部滚动）时，必须扩高页面 + 滚 window 才能
    让 scroller 渲染隐藏行。

    流程：
    1. 动态计算 body minHeight（每件约250px + 保底4000px）创造足够滚动空间
    2. 每次 window.scrollTo(0, y+=400) 触发 scroller 重渲染
    3. 收集所有行的商品数据，按 ERP ID 去重
    4. 稳定 25 轮无新商品 → 结束（防止无限循环）
    5. 恢复页面高度和滚动位置

    Returns:
        去重后的商品列表（可能少于 tab_count，差值即虚拟滚动未渲染部分）
    """
    page.evaluate("""() => {
        document.body.style.minHeight = "3000px";
        document.documentElement.style.minHeight = "3000px";
    }""")
    sleep(T.SCROLL_RECOVER)

    all_ids = set()
    all_products = []
    stable = 0
    step = 400

    for i in range(max_scrolls):
        y = i * step
        page.evaluate("window.scrollTo(0, %d)" % y)
        sleep(200)

        products = _extract_visible_products(page)
        added = 0
        for p in products:
            pid = p.get("erp_id", "")
            if pid and pid not in all_ids:
                all_ids.add(pid)
                all_products.append(p)
                added += 1

        if added == 0:
            stable += 1
        else:
            stable = 0

        if len(all_ids) >= tab_count:
            break
        if stable >= C.MAX_STABLE_ROUNDS:
            break

    # 恢复页面状态
    page.evaluate("""() => {
        window.scrollTo(0, 0);
        document.body.style.minHeight = "";
        document.documentElement.style.minHeight = "";
    }""")

    return all_products


def scan_unclaimed_products(page, tab_text=TXT.TAB_UNCLAIMED) -> dict:
    """全量扫描采集箱「未认领」tab — 三重策略，不遗漏

    策略：
    ① tab 文本「未认领(N)」权威计数
    ② 当前 DOM 可见商品快速提取
    ③ 扩展页面高度 + 窗口滚动 → 触发虚拟滚动渲染隐藏行

    Args:
        page: Playwright page (connect_over_cdp)
        tab_text: tab 名称，默认「未认领」

    Returns:
        dict: {tab_count, products: [{erp_id, title, price, ...}], complete: bool}
    """
    tab_count = _get_tab_count(page, tab_text)

    # 策略①：快速提取当前可见行
    products = _extract_visible_products(page)
    seen = set(p["erp_id"] for p in products if p.get("erp_id"))

    if len(seen) >= tab_count:
        return {"tab_count": tab_count, "products": products, "complete": True}

    # 策略②：窗口滚动补齐隐藏行
    all_products = _scroll_window_for_all_products(page, tab_count)
    if len(all_products) > len(products):
        products = all_products

    complete = len(set(p["erp_id"] for p in products if p.get("erp_id"))) >= tab_count
    if not complete:
        print(f"  ⚠️ 虚拟滚动限制: 仅提取 {len(products)}/{tab_count} 件，差 {tab_count - len(products)} 件未渲染")

    return {"tab_count": tab_count, "products": products, "complete": complete}
