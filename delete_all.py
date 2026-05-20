#!/usr/bin/env python3
import sys, time
sys.stdout.reconfigure(encoding='utf-8')
from infrastructure.config_loader import ConfigLoader
from infrastructure.browser import BrowserManager

_cfg = ConfigLoader().load()
bm = BrowserManager(cdp_ports=_cfg.erp_cdp_ports)
bm.connect()
page = bm.page

# go to collect box
page.goto(f'{_cfg.erp_url}/member/product/general/collect-box', wait_until='networkidle', timeout=30000)
time.sleep(3)

# 切未认领
page.locator('text=未认领').first.click()
time.sleep(3)

# 读所有商品ID
ids = page.evaluate("""() => {
    var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
    var list = [];
    rows.forEach(function(row) {
        var m = row.textContent.match(/货源ID[：:]\\s*(\\d+)/);
        if (m) list.push(m[1]);
    });
    return list;
}""")
print(f'未认领: {len(ids)} 个')

# 扩高页面+滚动确保所有行渲染
page.evaluate("""() => {
    document.body.style.minHeight = "8000px";
    document.documentElement.style.minHeight = "8000px";
}""")
time.sleep(0.3)
for i in range(60):
    page.evaluate(f'window.scrollTo(0, {i * 120})')
    time.sleep(0.15)

# 全选所有checkbox — 不管是否可见行
checked = page.evaluate("""() => {
    var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
    var n = 0;
    rows.forEach(function(row) {
        var cb = row.querySelector('input[type="checkbox"]');
        if (cb && !cb.checked) {
            cb.checked = true;
            cb.dispatchEvent(new Event('change', {bubbles: true}));
            n++;
        }
    });
    return n;
}""")
print(f'勾选: {checked} 个')

if checked == 0:
    print('无商品可删除')
    bm.disconnect()
    exit()

# 恢复高度
page.evaluate("""() => { window.scrollTo(0, 0); document.body.style.minHeight = ''; document.documentElement.style.minHeight = ''; }""")
time.sleep(0.3)

# 点删除按钮
page.evaluate("""() => {
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
        if (btns[i].offsetParent && btns[i].textContent.includes('删除') && btns[i].className.includes('t-button--variant-base')) {
            btns[i].click();
            return;
        }
    }
}""")
time.sleep(1)

# 确认弹窗
page.evaluate("""() => {
    var ds = document.querySelectorAll('[class*="dialog"]');
    for (var i = 0; i < ds.length; i++) {
        if (!ds[i].offsetParent) continue;
        var btns = ds[i].querySelectorAll('button');
        for (var j = 0; j < btns.length; j++) {
            if (btns[j].offsetParent && btns[j].textContent.trim() === '确认') {
                btns[j].click();
                return;
            }
        }
    }
    // 兜底
    var confirms = document.querySelectorAll('.t-dialog__confirm');
    for (var i = 0; i < confirms.length; i++) {
        if (confirms[i].offsetParent) { confirms[i].click(); return; }
    }
}""")
print('删除确认已点')
time.sleep(3)

# 关失败详情弹窗
page.evaluate("""() => {
    var ds = document.querySelectorAll('[class*="dialog"]');
    ds.forEach(function(d) {
        if (d.offsetParent) {
            var c = d.querySelector('.t-dialog__close');
            if (c && typeof c.click === 'function') c.click();
        }
    });
}""")

print('删除完成 ✅')
bm.disconnect()
