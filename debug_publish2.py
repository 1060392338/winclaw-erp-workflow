#!/usr/bin/env python3
"""发布断布机到顺顺小屋童装 - 完整流程"""
import sys, time, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
p = sync_playwright().start()
b = p.chromium.connect_over_cdp('http://127.0.0.1:9223')

# 找到发布页tab
page = None
for ctx in b.contexts:
    for pg in ctx.pages:
        if 'publish' in pg.url:
            page = pg
            break
if not page:
    print('NO_PUBLISH_TAB')
    p.stop()
    exit()

# 1. 切草稿箱
page.locator('text=草稿箱').first.click()
time.sleep(1.5)

# 2. 选顺顺店铺
tags = page.locator('.t-tag--check')
for i in range(tags.count()):
    if '順順' in tags.nth(i).text_content():
        tags.nth(i).click()
        break
time.sleep(0.5)

# 3. 查询
page.locator('button:has-text("查询")').first.click()
time.sleep(4)

# 4. 只勾选断布机，取消其他
page.evaluate("""() => {
    // 全部取消
    document.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = false; });
    // 勾选断布机
    var rows = document.querySelectorAll('[class*="virtual-table-tr"]');
    for(var i=0;i<rows.length;i++) {
        if(rows[i].textContent.includes('626005526840')) {
            var cb = rows[i].querySelector('input[type="checkbox"]');
            if(cb) { cb.checked = true; cb.dispatchEvent(new Event('change', {bubbles:true})); }
        }
    }
}""")
time.sleep(0.5)

# 检查勾选数
checked = page.evaluate("""() => {
    var cbs = document.querySelectorAll('input[type="checkbox"]:checked');
    return cbs.length;
}""")
print(f'已勾选: {checked} 个')

# 5. 触发产品发布下拉
# 先hover在按钮上
page.locator('button:has-text("产品发布")').first.hover()
time.sleep(0.5)
# 再click
page.locator('button:has-text("产品发布")').first.click()
time.sleep(2)

# 6. 检查下拉菜单（可能以popup/dropdown形式出现）
dd = page.locator('.t-dropdown__item-text')
print(f'下拉项数: {dd.count()}')
for i in range(dd.count()):
    print(f'  [{i}] {dd.nth(i).text_content()}')

# 如果下拉为空，检查其他选择器
if dd.count() == 0:
    dd2 = page.locator('[class*="dropdown"]')
    print(f'dropdown容器: {dd2.count()}')
    dd3 = page.locator('[class*="select-option"]')
    print(f'select-option: {dd3.count()}')
    dd4 = page.locator('[class*="popup"]')
    print(f'popup: {dd4.count()}')

# 7. 点击立即发布
if dd.count() > 0:
    # 用JS点击
    page.evaluate("""() => {
        var items = document.querySelectorAll('.t-dropdown__item-text');
        for(var i=0;i<items.length;i++) {
            if(items[i].textContent.trim() === "立即发布") {
                items[i].click();
                return;
            }
        }
    }""")
    print('已点立即发布')
else:
    print('无下拉菜单')
    b.close(); p.stop()
    exit()

# 8. 等弹窗 - 轮询10秒
time.sleep(1)
for _ in range(20):
    time.sleep(0.5)
    info = page.evaluate("""() => {
        var ds = document.querySelectorAll('[class*="dialog"]');
        for(var i=0;i<ds.length;i++) {
            if(!ds[i].offsetParent) continue;
            var btns = [];
            ds[i].querySelectorAll('button').forEach(function(b){if(b.offsetParent) btns.push(b.textContent.trim());});
            return JSON.stringify({text: ds[i].textContent.substring(0,300), btns: btns});
        }
        return null;
    }""")
    if info:
        info = json.loads(info)
        print(f'弹窗: {info["text"][:80]}')
        print(f'按钮: {info["btns"]}')
        
        btns = info['btns']
        # 先找保存
        clicked = False
        for b in btns:
            if '保存' in b:
                page.evaluate('() => { document.querySelectorAll("[class*=dialog] button").forEach(function(x){if(x.offsetParent && x.textContent.trim()=="' + b + '") x.click();}); }')
                print(f'✅ 点: {b}')
                clicked = True
                break
        if clicked:
            time.sleep(3)
            print('发布成功!')
            break
        
        # 未设置类目 -> 跳过
        for b in btns:
            if '跳过' in b:
                page.evaluate('() => { document.querySelectorAll("[class*=dialog] button").forEach(function(x){if(x.offsetParent && x.textContent.trim()=="' + b + '") x.click();}); }')
                print(f'点: {b}')
                clicked = True
                break
        if clicked:
            time.sleep(2)
            continue
        
        # 确认/确定
        for b in btns:
            if b in ('确认','确定'):
                page.evaluate('() => { document.querySelectorAll("[class*=dialog] button").forEach(function(x){if(x.offsetParent && x.textContent.trim()=="' + b + '") x.click();}); }')
                print(f'点: {b}')
                clicked = True
                break
        if clicked:
            time.sleep(2)
            continue
        
        print('无法处理弹窗，退出')
        break
else:
    print('未检测到弹窗')

# 9. 切发布中看结果
time.sleep(2)
try:
    page.locator('text=发布中').first.click()
    time.sleep(2)
    body = page.evaluate('document.body.innerText')
    if '626005526840' in body:
        print('断布机在发布中 ✅')
    else:
        print('断布机不在发布中')
except Exception as e:
    print(f'发布中tab: {e}')

b.close()
p.stop()
