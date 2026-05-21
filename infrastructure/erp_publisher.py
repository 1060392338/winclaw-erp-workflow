"""ERP认领+Shopee发布操作

输入：合规审查通过的 Product ID 列表
流程：采集箱勾选→认领→选择店铺→Shopee发布页→暂不上架→发布

⚠️ 选择器说明：
  货憨憨ERP使用 TDesign (Vue) UI组件库，非Element UI。
  选择器使用 .t-* 前缀。以下选择器基于实测待验证，标注了备用方案。
"""

from playwright.sync_api import Page


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
    DIALOG_BODY = ".t-dialog__body"
    DIALOG_FOOTER = ".t-dialog__footer"
    DIALOG_CLOSE = ".t-dialog__close"          # 关闭按钮
    CLAIM_MODAL = '[class*="dialog"]:visible'   # 认领弹窗
    STORE_TAG = '[class*="select-block-item"]'  # 店铺选择标签
    DROPDOWN_ITEM = '[class*="select-option"], [class*="option-item"]'
    SUCCESS_TOAST = '[class*="message--success"], [class*="t-message--success"]'
    CLAIM_CONFIRM = '确定'                       # 认领确认（可见的那个）

    def __init__(self, page: Page):
        self.page = page

    def navigate_to_publish(self):
        """导航到Shopee产品发布页"""
        self.page.goto(self.get_publish_url())
        self.page.wait_for_load_state("networkidle", timeout=30000)

    def navigate_to_collection_box(self):
        """导航到采集箱（三重保障：慢速+等待+重试）"""
        import time as _time
        max_retry = 3
        for attempt in range(max_retry):
            try:
                # 先用 wait_until=domcontentloaded 减少导航冲突窗口
                self.page.goto(self.get_collect_box_url(), wait_until="domcontentloaded", timeout=60000)
                # 等渲染稳定后再等网络空闲
                _time.sleep(3)
                self.page.wait_for_load_state("networkidle", timeout=60000)
                break
            except Exception as e:
                if attempt < max_retry - 1:
                    print(f"  ⚠️ 导航采集箱被中断，第{attempt+2}次重试...", flush=True)
                    _time.sleep(2)
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
            if btn.is_visible(timeout=3000):
                btn.click()
                clicked = True
        except:
            pass
        if not clicked:
            try:
                btn = self.page.locator("button:has-text('认领')").last
                if btn.is_visible(timeout=3000):
                    btn.click()
                    clicked = True
            except:
                pass
        if not clicked:
            self.page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes('认领') && btn.offsetParent !== null) {
                        btn.click(); return;
                    }
                }
            }""")
        if not clicked:
            print("  ⚠️ 点击认领按钮失败（3种方案均未找到）", flush=True)
        self.page.wait_for_load_state("networkidle", timeout=30000)

    def get_store_list_from_modal(self) -> list[dict]:
        """从认领弹窗中动态提取店铺列表（不硬编码，根据实际账号返回）

        货憨憨认领弹窗表单结构：
        电商平台：Shopee  ← .select-block-item (平台)
        地区：全部 台湾    ← .select-block-item (地区筛选)
        店铺：全部 吉象星連坊 順順の小屋童裝 ...  ← 真正的店铺列表

        策略：找「店铺」label → 取其容器内所有 .select-block-item（排除"全部"）
        """
        # 方案1：按「店铺」label 定位 → 同级容器中的店铺checkbox/label
        stores = self.page.evaluate("""() => {
            const dialog = document.querySelector('[class*="dialog"]:not([style*="display: none"])');
            if (!dialog) return [];

            // 找「店铺」label
            const labels = dialog.querySelectorAll('label, [class*="label"]');
            let storeSection = null;
            labels.forEach(l => {
                if (l.textContent.trim() === '店铺') {
                    let el = l.parentElement;
                    while (el && el !== dialog) {
                        if (el.classList.contains('t-form__item')) {
                            storeSection = el;
                            break;
                        }
                        el = el.parentElement;
                    }
                }
            });
            if (!storeSection) return [];

            // 从 checkbox-group 和 select-block-item 两路提取
            const seen = new Set();
            const stores = [];
            
            // 路A: label元素（t-checkbox-group label）
            const cbLabels = storeSection.querySelectorAll('[class*="checkbox-group"] label');
            cbLabels.forEach(el => {
                const t = el.textContent.trim();
                if (t && t !== '全部' && !seen.has(t)) {
                    seen.add(t);
                    stores.push({ store_id: '', store_name: t, platform: 'Shopee' });
                }
            });
            
            // 路B: select-block-item 标签
            const blocks = storeSection.querySelectorAll('[class*="select-block-item"]');
            blocks.forEach(item => {
                const t = item.textContent.trim();
                if (t && t !== '全部' && t !== 'Shopee' && !t.includes('台湾') && !seen.has(t)) {
                    seen.add(t);
                    stores.push({
                        store_id: item.getAttribute('data-id') || item.getAttribute('data-value') || '',
                        store_name: t,
                        platform: 'Shopee',
                    });
                }
            });
            
            return stores;
        }""")

        if stores:
            return stores

        # 方案2兜底：扫所有 select-block-item，过滤非店铺
        blocks = self.page.locator(self.STORE_TAG).all()
        all_items = self._parse_store_blocks(blocks)
        return [s for s in all_items if s["store_name"] not in ("Shopee", "全部", "台湾")]

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

        三种定位策略：
        1. t-checkbox-group label 文本匹配
        2. select-block-item 匹配
        3. JS 兜底点击
        """
        # 方案1: checkbox-group label
        label = self.page.locator(
            f"[class*='checkbox-group'] label:has-text('{store_name}')"
        ).first
        if label.is_visible():
            label.click()
            return

        # 方案2: select-block-item
        block = self.page.locator(
            f"{self.STORE_TAG}:has-text('{store_name}')"
        ).first
        if block.is_visible():
            block.click()
            return

        # 方案3: JS 兜底
        self.page.evaluate("""(storeName) => {
            const dialog = document.querySelector('[class*="dialog"]:not([style*="display: none"])');
            if (!dialog) return false;
            const items = dialog.querySelectorAll(
                '[class*="checkbox-group"] label, [class*="select-block-item"]'
            );
            for (const el of items) {
                if (el.textContent.trim().includes(storeName)) {
                    el.click();
                    return true;
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
        confirm.click()
        self.page.wait_for_load_state("networkidle", timeout=30000)

    def filter_by_store(self, store_name: str):
        """在发布页按店铺名筛选"""
        self.page.locator("[placeholder*='店铺']").click()
        self.page.locator(f"text={store_name}").click()
        self.page.wait_for_load_state("networkidle", timeout=30000)

    def set_no_listing(self):
        """设置「发布后暂不上架」（安全红线）"""
        self.page.locator("button:has-text('发布配置')").click()
        self.page.wait_for_load_state("networkidle", timeout=30000)
        self.page.locator("text=暂不上架").click()
        self.page.locator("button:has-text('确定')").click()

    def publish_now(self):
        """产品发布 → 立即发布 → 确认"""
        self.page.locator("button:has-text('产品发布')").click()
        self.page.wait_for_load_state("networkidle", timeout=30000)
        self.page.locator("text=立即发布").click()
        self.page.locator("button:has-text('确定')").click()
        self.page.wait_for_load_state("networkidle", timeout=30000)

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
        self.page.wait_for_load_state("networkidle", timeout=30000)
        rows = self.page.locator("table tbody tr").count()
        return f"done ({rows} items)"


def _get_tab_count(page, tab_text="未认领") -> int:
    """从tab标签读取计数，如「未认领(10)」→ 10"""
    count = page.evaluate("""(tab) => {
        const tabs = document.querySelectorAll('[class*="tab"]');
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


def _get_collect_box_pages(page, tab_text="未认领") -> int:
    """获取采集箱指定tab的总页数"""
    total = page.evaluate("""() => {
        const pag = document.querySelector('.t-pagination');
        if (!pag) return 1;
        const items = pag.querySelectorAll('.t-pagination__number');
        const nums = Array.from(items).map(n => parseInt(n.textContent)).filter(n => !isNaN(n));
        return Math.max(...nums, 1);
    }""")
    return total


def _check_ids_on_page(page, reject_ids: set, tab_text="未认领") -> int:
    """在当前页勾选匹配的reject_ids，返回勾选数

    双引擎扫描策略（2026-05-19 修复）：
    ① scrollHeight > clientHeight → 内部滚动（scroller.scrollTop）
    ② scrollHeight == clientHeight → 窗口扩高+滚动（window.scrollTo）
    """
    total_checked = 0
    reject_list = list(reject_ids)

    # 检查 scroller 状态，选引擎
    s = page.evaluate("""() => {
        const s = document.querySelector('.vue-recycle-scroller');
        return s ? {h: s.scrollHeight, ch: s.clientHeight} : null;
    }""")
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
    s = page.evaluate("""() => {
        const s = document.querySelector('.vue-recycle-scroller');
        return s ? {h: s.scrollHeight, ch: s.clientHeight} : null;
    }""")
    if not s:
        return 0

    reject_set = set(reject_ids)
    for pass_n in range(3):
        step = 80
        max_pos = max(0, s["h"] - s["ch"])
        for pos in range(0, max_pos + step, step):
            page.evaluate(f"() => {{ const s = document.querySelector('.vue-recycle-scroller'); if(s) s.scrollTop = {min(pos, max_pos)}; }}")
            page.wait_for_timeout(150)

        page.evaluate("() => { const s = document.querySelector('.vue-recycle-scroller'); if(s) s.scrollTop = 0; }")
        page.wait_for_timeout(300)

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
    page.wait_for_timeout(500)

    for i in range(60):
        page.evaluate("window.scrollTo(0, %d)" % (i * 150))
        page.wait_for_timeout(300)

        checked = _check_visible_checkboxes(page, reject_set)
        total_checked += checked

        # 连续5次无新增 → 退出
        if checked == 0:
            stable_count = sum(1 for j in range(max(0,i-4), i+1) if True)
            if stable_count >= 5:
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
    """从采集箱批量删除不合规商品（支持分页+虚拟滚动）

    遍历所有分页，逐页勾选匹配的reject_ids，最后统一批量删除。

    Args:
        page: Playwright page (connect_over_cdp)
        reject_ids: ERP ID 列表

    Returns:
        实际删除数量
    """
    if not reject_ids:
        return 0

    reject_set = set(str(i) for i in reject_ids)
    print(f"\n  🗑️  删除 {len(reject_set)} 个不合规商品...")

    try:
        # 切回采集箱未认领tab
        page.goto(ERPPublisher.get_collect_box_url())
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_selector(".virtual-table-container", timeout=10000)
        page.locator("text=未认领").first.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_selector(".virtual-table-container", timeout=10000)

        # 读取tab权威计数
        tab_count = _get_tab_count(page)
        print(f"    未认领: {tab_count} 件（页面计数）")

        # 遍历所有分页
        total_pages = _get_collect_box_pages(page)
        total_checked = 0

        for pg in range(1, total_pages + 1):
            if pg > 1:
                # 切到下一页
                page.evaluate(f"""((n) => {{
                    const pages = document.querySelectorAll('.t-pagination__number');
                    for (const p of pages) {{
                        if (parseInt(p.textContent) === n) {{ p.click(); return; }}
                    }}
                }})""", pg)
                page.wait_for_load_state("networkidle", timeout=15000)
                page.wait_for_selector(".virtual-table-container", timeout=10000)
                page.wait_for_timeout(1500)

            checked = _check_ids_on_page(page, reject_set)
            if checked:
                print(f"    第{pg}页: 勾选 {checked} 个")
                total_checked += checked

        if total_checked == 0:
            print("  ⚠️ 未找到待删除商品")
            return 0

        # 点批量删除按钮
        page.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const btn of btns) {
                if (btn.textContent.includes('删除') && btn.classList.contains('t-button--variant-base')) {
                    btn.click(); return;
                }
            }
        }""")

        # 等确认弹窗
        page.wait_for_timeout(1000)
        page.evaluate("""() => {
            var btns = document.querySelectorAll('[class*="dialog"] button');
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].offsetParent && btns[i].textContent.trim() === '确认') {
                    btns[i].click(); return;
                }
            }
            // 兜底
            var confirms = document.querySelectorAll('.t-dialog__confirm');
            for (var i = 0; i < confirms.length; i++) {
                if (confirms[i].offsetParent) { confirms[i].click(); return; }
            }
        }""")

        page.wait_for_timeout(2000)
        # 关失败详情弹窗（如果有）
        page.evaluate("""() => {
            const closes = document.querySelectorAll('.t-dialog__close');
            for (const c of closes) c.click();
        }""")

        print(f"  ✅ 已从采集箱批量删除 {total_checked} 个")
        
        # 🔴 追加删除：被拒商品可能因虚拟滚动只删了部分，再扫描剩余未删的
        remaining = reject_set.copy()  # 已经删的部分和原有一起传
        retry_count = 0
        while retry_count < 5:
            # 重新扫描当前页是否有未删的
            more = _check_ids_on_page(page, remaining)
            if more == 0:
                break
            total_checked += more
            print(f"  🔄 追加删除 {more} 个（第{retry_count+2}轮）")
            
            # 点批量删除
            page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const btn of btns) {
                    if (btn.textContent.includes('删除') && btn.classList.contains('t-button--variant-base')) {
                        btn.click(); return;
                    }
                }
            }""")
            page.wait_for_selector(".t-dialog__confirm", timeout=8000)
            page.evaluate("""() => {
                const confirms = document.querySelectorAll('.t-dialog__confirm');
                for (const btn of confirms) { btn.click(); return; }
            }""")
            page.wait_for_timeout(2000)
            # 关失败弹窗
            page.evaluate("""() => {
                const closes = document.querySelectorAll('.t-dialog__close');
                for (const c of closes) c.click();
            }""")
            retry_count += 1

        print(f"  ✅ 累计从采集箱删除 {total_checked} 个不合规商品")
        print()
        return total_checked

    except Exception as e:
        print(f"  ⚠️ 删除操作异常: {e}")
        print("  ℹ️  可尝试手动删除或重新运行 --delete-rejected")
        return 0


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
    1. document body+html minHeight=3000px 创造滚动空间
    2. 每次 window.scrollTo(0, y+=200) 触发 scroller 重渲染
    3. 收集所有行的商品数据，按 ERP ID 去重
    4. 稳定 15 轮无新商品 → 结束（防止无限循环）
    5. 恢复页面高度和滚动位置

    Returns:
        去重后的商品列表（可能少于 tab_count，差值即虚拟滚动未渲染部分）
    """
    page.evaluate("""() => {
        document.body.style.minHeight = "3000px";
        document.documentElement.style.minHeight = "3000px";
    }""")
    page.wait_for_timeout(300)

    all_ids = set()
    all_products = []
    stable = 0
    step = 200

    for i in range(max_scrolls):
        y = i * step
        page.evaluate("window.scrollTo(0, %d)" % y)
        page.wait_for_timeout(500)

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
        if stable > 15:
            break

    # 恢复页面状态
    page.evaluate("""() => {
        window.scrollTo(0, 0);
        document.body.style.minHeight = "";
        document.documentElement.style.minHeight = "";
    }""")

    return all_products


def scan_unclaimed_products(page, tab_text="未认领") -> dict:
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
