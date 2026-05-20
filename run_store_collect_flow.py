#!/usr/bin/env python3
"""PDD搜索店铺 → 进店 → 销量排序 → 采集top2(去重) → 合规审查(LLM) → 认领(用户确认)
基于2026-05-18跑通流程：DrissionPage连9223 + UI下拉框 + 不杀浏览器

Agent 人设: 搜货手 (CollectorAgent)
  - 老练电商采购，PDD采集三年经验
  - 稳健型选手，随机延迟防反爬
  - 宁慢一分，不抢一秒
  - 如实汇报采集结果，不编造数据
参见: agent_prompts.PROMPT_COLLECTOR, PROMPT_COLLECTOR_RETRY"""
import sys, time, random, re, json
from pathlib import Path
from dotenv import load_dotenv

PROJECT = Path(__file__).parent
sys.path.insert(0, str(PROJECT))
load_dotenv(PROJECT / ".env")

from models.schema import Product, ComplianceResult
from infrastructure.compliance_checker import ComplianceChecker
from infrastructure.image_checker import ImageChecker
from infrastructure.taiwan_regulation import TaiwanRegulation
from infrastructure.title_optimizer import TitleOptimizer


def search_store_and_collect(shop_name: str, top_n: int = 2, keyword: str = "") -> list[dict]:
    """搜索店铺 → 进店 → 销量排序 → (关键词筛选) → 采集top N
    
    基于2026-05-18跑通流程：
    1. DrissionPage连接已有Chrome(9223)，保留登录态，绝不quit
    2. UI下拉框：点击商品▼ → 选店铺 → search_type=mall
    3. 两步进店：点搜索结果中的店名 → 点"进店"卡片
    4. 反爬：实时取坐标、随机延迟、elementFromPoint点击
    5. keyword非空 → 进店后在店内搜索该关键词
    """
    from DrissionPage import ChromiumPage
    import json as _json
    
    print(f"\n🔍 PDD搜索店铺: {shop_name}")
    
    from infrastructure.config_loader import ConfigLoader
    _sc_cfg = ConfigLoader().load()
    _sc_port = _sc_cfg.erp_cdp_ports[0]
    page = ChromiumPage(addr_or_opts=f"127.0.0.1:{_sc_port}")
    results = []
    
    try:
        # 导航PDD首页
        page.get("https://mobile.yangkeduo.com/")
        time.sleep(6 + random.uniform(0, 2))
        
        if "login" in page.url.lower():
            return [{"error": "PDD需要登录，请手动扫码"}]
        
        # 点击搜索栏
        page.run_js("var d=document.querySelector('[class*=\"2fnObgNt\"]');if(d)d.click();")
        time.sleep(3 + random.uniform(0, 1))
        
        # UI下拉框：商品▼ → 店铺
        page.run_js("""
var all=document.querySelectorAll('*');
for(var i=0;i<all.length;i++){
    var t=all[i].textContent.trim(),c=all[i].className||'';
    if(t==='商品'&&c.indexOf('2Bhbnb2b')>-1){all[i].click();break;}
}
""")
        time.sleep(1)
        shop_opt = page.run_js("""
return(function(){var lis=document.querySelectorAll('li');
for(var i=0;i<lis.length;i++){if(lis[i].textContent.trim()==='店铺'){
var r=lis[i].getBoundingClientRect();return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});}}return'nf';})()
""")
        if shop_opt != 'nf':
            s = _json.loads(shop_opt)
            page.run_js(f"document.elementFromPoint({s['x']:.0f},{s['y']:.0f}).click()")
            time.sleep(1)
        
        # 输入搜索词（用 value 赋值替代原生 setter，PDD 已拦截 getOwnPropertyDescriptor）
        page.run_js(f"""var inp=document.querySelector('input[type=\"search\"]')||document.querySelector('input[type=\"text\"]');
if(!inp){{var inputs=document.querySelectorAll('input');for(var i=0;i<inputs.length;i++){{
var r=inputs[i].getBoundingClientRect();if(r.width>100&&r.y<200&&inputs[i].offsetParent){{inp=inputs[i];break;}}}}}}
inp.value='{shop_name}';inp.dispatchEvent(new Event('input',{{bubbles:true}}));inp.dispatchEvent(new Event('change',{{bubbles:true}}));
""")
        time.sleep(random.uniform(0.3, 0.8))
        
        # 点"搜索"按钮
        page.run_js("var all=document.querySelectorAll('*');for(var i=0;i<all.length;i++){if(all[i].textContent.trim()==='搜索'&&all[i].offsetParent){var r=all[i].getBoundingClientRect();if(r.width>15&&r.y<200){all[i].click();break;}}}")
        time.sleep(6 + random.uniform(0, 2))
        
        url = page.url
        text = page.run_js("return document.body.innerText.substring(0,500)")
        print(f"  搜索后URL: {url[:120]}")
        
        # 🔑 如果搜索没走店铺模式(search_type=mall)，直接导航到店铺搜索URL
        if "search_type=mall" not in url:
            print("  ⚠️ 未切到店铺模式，直接导航...")
            page.get(f"https://mobile.yangkeduo.com/search_result.html?search_key={shop_name}&search_type=mall")
            time.sleep(6)
            url = page.url
            text = page.run_js("return document.body.innerText.substring(0,500)")
            print(f"  重定向URL: {url[:120]}")
        
        if "login" in url.lower():
            return [{"error": "搜索触发登录重定向，Cookie可能过期"}]
        
        if "系统繁忙" in text or "稍后再试" in text:
            print("  ⚠️ 风控，冷却后重试...")
            time.sleep(10)
            page.get(f"https://mobile.yangkeduo.com/search_result.html?search_key={shop_name}&search_type=mall")
            time.sleep(6)
            if "login" in page.url.lower():
                return [{"error": "风控后登录重定向"}]
        
        # 两步进店：①点搜索结果中的店名(y>100跳过搜索栏)
        # 🔑 模糊匹配：去掉后缀 + 去掉最后1字符防PDD同音字替换(如城→诚)
        search_key = shop_name.replace("专卖店", "").replace("旗舰店", "").replace("官方店", "")
        if len(search_key) >= 5:
            search_key = search_key[:-1]  # 去掉可能被替换的最后一字
        print(f"  找店铺入口(匹配词: {search_key})...")
        store_items = page.run_js(f"""
return(function(){{var r=[],all=document.querySelectorAll('*');
for(var i=0;i<all.length;i++){{var t=all[i].textContent.trim();
if(t.indexOf('{search_key}')>-1&&t.length<100){{var rect=all[i].getBoundingClientRect();
if(rect.y>100&&rect.width>20&&rect.height>10)r.push({{x:rect.left+rect.width/2,y:rect.top+rect.height/2,text:t.substring(0,50)}});}}}}return JSON.stringify(r.slice(0,10));}})()
""")
        store_items = _json.loads(store_items) if store_items else []
        print(f"  列表项: {len(store_items)} 个")
        
        if not store_items:
            return [{"error": f"未找到'{shop_name}'店铺入口"}]
        
        # 点第一个(y>100的)
        si = store_items[0]
        page.run_js(f"document.elementFromPoint({si['x']:.0f},{si['y']:.0f}).click()")
        time.sleep(5 + random.uniform(0, 1))
        
        # ②找"进店"文字并点击
        enter_btn = page.run_js("""
return(function(){var all=document.querySelectorAll('*');
for(var i=0;i<all.length;i++){var t=all[i].textContent.trim();
if(t.indexOf('进店')>-1){var rect=all[i].getBoundingClientRect();
if(rect.y<window.innerHeight&&rect.width>20)return JSON.stringify({x:rect.left+rect.width/2,y:rect.top+rect.height/2});}}return'nf';})()
""")
        if enter_btn == 'nf':
            return [{"error": "未找到'进店'按钮"}]
        
        eb = _json.loads(enter_btn)
        page.run_js(f"document.elementFromPoint({eb['x']:.0f},{eb['y']:.0f}).click()")
        time.sleep(6 + random.uniform(0, 2))
        
        # 提取mall_id
        mall_id = page.run_js("""
return(function(){var m=window.location.href.match(/mall_id=(\\d+)/);if(m)return m[1];
var all=document.querySelectorAll('*');for(var i=0;i<all.length;i++){
m=(all[i].innerHTML||'').match(/mall_id=(\\d+)/);if(m)return m[1];}return'';})()
""")
        if not mall_id:
            return [{"error": "无法提取mall_id"}]
        
        print(f"  mall_id={mall_id}")
        
        # 直连店铺页
        if 'mall_page' not in page.url:
            page.get(f"https://mobile.yangkeduo.com/mall_page.html?mall_id={mall_id}")
            time.sleep(6 + random.uniform(0, 2))
        
        print(f"  店铺URL: {page.url[:100]}")
        
        # 🔑 关键词筛选：在店内搜索关键词（进店后、销量排序前）
        if keyword:
            print(f"  店内搜索关键词: {keyword}")
            page.run_js(f"""
var inp = document.querySelector('input[type=\"search\"]') || document.querySelector('input[type=\"text\"]');
if (!inp) {{
    var inputs = document.querySelectorAll('input');
    for (var i = 0; i < inputs.length; i++) {{
        var r = inputs[i].getBoundingClientRect();
        if (r.width > 80 && r.y < 300 && inputs[i].offsetParent) {{ inp = inputs[i]; break; }}
    }}
}}
if (inp) {{
    inp.value = '{keyword}';
    inp.dispatchEvent(new Event('input', {{bubbles: true}}));
    inp.dispatchEvent(new Event('change', {{bubbles: true}}));
    setTimeout(function() {{
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {{
            if (all[i].textContent.trim() === '搜索' && all[i].offsetParent) {{
                all[i].click(); break;
            }}
        }}
    }}, 500);
}}
""")
            time.sleep(5 + random.uniform(0, 2))
        
        # 按销量排序
        page.run_js("var all=document.querySelectorAll('*');for(var i=0;i<all.length;i++){if(all[i].textContent.trim()==='销量'){all[i].click();break;}}")
        time.sleep(4 + random.uniform(0, 1))
        
        # 等商品加载（模拟真人滚动）
        print("  等商品加载...")
        imgs_list = []
        for attempt in range(8):
            page.run_js(f"window.scrollBy(0,{random.randint(200,500)})")
            time.sleep(random.uniform(1.5, 3))
            imgs = page.run_js("""
return(function(){var imgs=document.querySelectorAll('img[src*="pddpic"],img[src*="goods"]');var v=[];
imgs.forEach(function(img){var r=img.getBoundingClientRect();
if(r.width>40&&r.x>=0&&r.y>=0&&r.y<window.innerHeight)v.push({x:r.x+r.width/2,y:r.y+r.height/2});});return JSON.stringify(v);})()
""")
            imgs_list = _json.loads(imgs) if imgs else []
            if len(imgs_list) >= top_n:
                break
        
        if len(imgs_list) < top_n:
            return [{"error": f"只有{len(imgs_list)}张商品图，不够{top_n}个"}]
        
        # 采集（反爬：每次实时取坐标 + 随机延迟 + 去重）
        print(f"  采集前{top_n}个...")
        collected_ids = set()
        for i in range(min(top_n * 2, 20)):  # 最多试20次，防重复
            if len(results) >= top_n:
                break
            
            # 实时取坐标
            fresh_imgs = page.run_js("""
return(function(){var imgs=document.querySelectorAll('img[src*="pddpic"],img[src*="goods"]');var v=[];
imgs.forEach(function(img){var r=img.getBoundingClientRect();
if(r.width>40&&r.x>=0&&r.y>=0&&r.y<window.innerHeight)v.push({x:r.x+r.width/2,y:r.y+r.height/2});});return JSON.stringify(v);})()
""")
            fresh = _json.loads(fresh_imgs) if fresh_imgs else []
            if not fresh:
                break
            
            # 取第一个图（销量排序后第一个就是销量最高）
            img = fresh[0]
            time.sleep(random.uniform(0.5, 1.5))
            page.run_js(f"document.elementFromPoint({img['x']:.0f},{img['y']:.0f}).click()")
            time.sleep(5 + random.uniform(0, 2))
            
            m = re.search(r'goods_id=(\d+)', page.url)
            goods_id = m.group(1) if m else ""
            
            if not goods_id:
                page.run_js("history.back()")
                time.sleep(3 + random.uniform(0, 1))
                continue
            
            # 去重
            if goods_id in collected_ids:
                print(f"    ⏭ 跳过重复: goods_id={goods_id}")
                page.run_js("history.back()")
                time.sleep(4 + random.uniform(0.5, 1))
                # 滚动过已采集的商品
                page.run_js(f"window.scrollBy(0, {random.randint(300, 500)})")
                time.sleep(3)
                continue
            
            collected_ids.add(goods_id)
            time.sleep(random.uniform(1, 2))
            collected = page.run_js(
                "var b=document.querySelector('[class*=\"hhh_collect-button\"][type=\"primary\"]');"
                "if(b){b.click();return true;}return false;")
            print(f"    商品{len(results)+1}: goods_id={goods_id} collected={bool(collected)}")
            
            results.append({
                "goods_id": goods_id,
                "collected": bool(collected),
                "index": len(results) + 1
            })
            
            page.run_js("history.back()")
            time.sleep(4 + random.uniform(0.5, 1.5))
            # 滚动过已采集商品，确保下次看到不同商品
            page.run_js(f"window.scrollBy(0, {random.randint(300, 500)})")
            time.sleep(3)  # 等页面渲染稳定
    
    finally:
        # ⚠️ 红线：绝不quit浏览器！
        pass
    
    return results


def main():
    # 从命令行读取店铺名，支持多个店铺
    import argparse
    parser = argparse.ArgumentParser(description="PDD采集 → 合规 → 认领")
    parser.add_argument("shops", nargs="*", help="PDD店铺名(可多个)，--delete-rejected 模式可不填")
    parser.add_argument("-n", "--topn", type=int, default=2, help="每店采集前N个商品(默认2)")
    parser.add_argument("--target", help="认领目标Shopee店铺(如'順順の小屋童裝')，不提供则列出店铺让用户选")
    parser.add_argument("--keyword", "-k", help="店内搜索关键词（如'垃圾桶''数据线'），不提供则收集店铺全部商品")
    parser.add_argument("--delete-rejected", action="store_true",
                       help="删除不合规商品（从.claim_state.json读取reject_ids，由搜货手执行）")
    cargs = parser.parse_args()

    # --delete-rejected 独立处理（搜货手负责从采集箱删除）
    if cargs.delete_rejected:
        import json as _json
        state_file = PROJECT / ".claim_state.json"
        if not state_file.exists():
            print("❌ 无状态文件，请先运行合规审查")
            return 1
        state = _json.loads(state_file.read_text(encoding="utf-8"))
        rids = state.get("reject_ids", [])
        if not rids:
            print("ℹ️  无不合规商品需删除")
            return 0
        print(f"🗑️  搜货手删除 {len(rids)} 个不合规商品: {', '.join(rids)}")
        # 使用 Playwright 连接 Chrome 执行删除（与采集脚本共用浏览器）
        from playwright.sync_api import sync_playwright
        from infrastructure.erp_publisher import delete_rejected_products
        with sync_playwright() as pw:
            from infrastructure.config_loader import ConfigLoader
            _sc_cfg2 = ConfigLoader().load()
            _sc_port2 = _sc_cfg2.erp_cdp_ports[0]
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{_sc_port2}")
            # 复用已有页面的登录态（新建页面无session）
            page = browser.contexts[0].pages[0] if browser.contexts[0].pages else browser.contexts[0].new_page()
            delete_rejected_products(page, rids)
            browser.close()
        # 清理状态文件
        state["reject_ids"] = []
        state_file.write_text(_json.dumps(state, ensure_ascii=False, indent=2))
        if not state.get("pass_ids"):
            state_file.unlink(missing_ok=True)
        return 0
    shop_names = cargs.shops
    if not shop_names:
        parser.print_usage()
        print("❌ 请指定店铺名（--delete-rejected 模式已处理，正常模式必填 shops）")
        return 1
    target_store = cargs.target
    keyword = cargs.keyword or ""
    top_n = cargs.topn
    
    print("=" * 60)
    print(f"🔄 PDD店铺搜索 → 采集 → 合规 → 认领 全链路")
    print(f"   店铺: {', '.join(shop_names)}, 每店top{top_n}" + (f", 关键词={keyword}" if keyword else ""))
    print("=" * 60)
    
    all_collected = []
    for sn in shop_names:
        print(f"\n{'─'*40}\n📍 店铺: {sn}")
        collected = search_store_and_collect(sn, top_n=top_n, keyword=keyword)
        
        if not collected or collected[0].get("error"):
            err = collected[0].get("error", "采集失败") if collected else "无结果"
            print(f"  ❌ {sn} 采集失败: {err}")
            continue
        
        goods_count = sum(1 for c in collected if c.get("collected"))
        print(f"  ✅ {sn}: {goods_count}/{len(collected)} 个商品")
        all_collected.extend(collected)
    
    if not all_collected:
        print("\n❌ 所有店铺采集失败")
        return 1
    
    goods_count = sum(1 for c in all_collected if c.get("collected"))
    print(f"\n✅ PDD采集完成: {goods_count}/{len(all_collected)} 个商品")
    
    # ── Step 1: ERP操作（复用同一Chrome，不杀不重启）──
    print("\n[1/3] ERP采集箱...")
    from DrissionPage import ChromiumPage
    
    from infrastructure.config_loader import ConfigLoader
    _sc_cfg = ConfigLoader().load()
    _sc_port = _sc_cfg.erp_cdp_ports[0]
    page = ChromiumPage(addr_or_opts=f"127.0.0.1:{_sc_port}")
    
    # 导航ERP
    from infrastructure.config_loader import ConfigLoader
    _sc_cfg3 = ConfigLoader().load()
    page.get(f"{_sc_cfg3.erp_url}/member/home/index")
    time.sleep(5)
    page.get(f"{_sc_cfg3.erp_url}/member/product/general/collect-box")
    time.sleep(5)
    
    # 关弹窗
    page.run_js("""document.querySelectorAll('[class*="dialog"]').forEach(function(d){
        var cb=d.querySelector('[class*="close"]');if(cb&&typeof cb.click==='function')cb.click();});""")
    time.sleep(2)
    
    # 切未认领
    page.ele('@@text():未认领').click()
    time.sleep(4)
    
    # 提取商品
    raw = page.run_js("""
return(function(){
    var c=document.querySelector('.virtual-table-container');
    if(!c)return JSON.stringify([]);
    var t=c.textContent.replace(/\\\\u200b/g,'');
    var ids=[...t.matchAll(/货源ID[：:]\\\\s*(\\\\d+)/g)].map(function(m){return m[1];});
    var prices=[...t.matchAll(/CNY\\\\s*([\\\\d.]+)/g)].map(function(m){return m[1];});
    var result=[];
    for(var i=0;i<ids.length;i++){result.push({erp_id:ids[i],price:prices[i]?parseFloat(prices[i]):0});}
    var segs=t.split(/货源ID[：:]\\\\s*\\\\d+/);
    var imgs=c.querySelectorAll('img');
    for(var i=0;i<result.length;i++){
        if(i+1<segs.length){
            var m=segs[i+1].match(/([\\\\u4e00-\\\\u9fa5][\\\\u4e00-\\\\u9fa5\\\\-\\\\s\\\\w]{5,60})/);
            result[i].title=m?m[1].trim():'';
        }
        if(i<imgs.length)result[i].img_url=imgs[i].src||'';
    }
    return JSON.stringify(result);
})()
""")
    raw = json.loads(raw) if raw else []
    
    print(f"  未认领: {len(raw)} 件")
    if not raw:
        print("  ⚠️ 无未认领商品（采集可能未到账，刷新重试）")
        return 1
    
    for r in raw:
        print(f"    {r.get('erp_id','?')}: {r.get('title','?')[:50]} CNY{r.get('price',0)}")
    
    # ── 合规审查（纯LLM内部判断，不操作浏览器）──
    print("\n[2/4] 合规审查...")
    image_checker = ImageChecker()
    regulation = TaiwanRegulation()
    title_optimizer = TitleOptimizer(regulation_checker=regulation)
    checker = ComplianceChecker(image_checker, regulation, title_optimizer)
    
    products = []
    for r in raw:
        products.append(Product(
            id=r.get("erp_id", ""),
            title=r.get("title", "?")[:80],
            price=r.get("price", 0),
            shop_name=shop_names[0],
            category="",
            image_urls=[r.get("img_url", "")] if r.get("img_url") else [],
            erp_internal_id=r.get("erp_id", ""),
        ))
    
    results = checker.review_batch_concurrent(products, max_workers=5)
    
    print(f"\n  {'─'*50}")
    for r in results:
        icon = {"pass":"✅","reject":"❌","title_optimized":"🔧"}.get(r.final_status,"❓")
        print(f"  {icon} [{r.final_status}] {r.product.title[:60]}")
        if r.image_issues:
            for issue in r.image_issues:
                print(f"      📷 图片: {issue}")
        if r.title_issues:
            for issue in r.title_issues:
                print(f"      📝 标题: {issue}")
        if r.optimized_title:
            print(f"      🔧 优化: {r.optimized_title[:80]}")
    
    print(f"  {'─'*50}")
    print(f"\n  {checker.get_summary(results)}")
    
    pass_ids = checker.get_pass_ids(results)
    if not pass_ids:
        print("  ⚠️ 无合规商品，跳过认领")
        return 0
    
    # ── 认领（不自动决策，返回店铺列表给用户确认）──
    print(f"\n[3/4] 认领 {len(pass_ids)} 个合规商品...")
    
    # 勾选商品
    page.run_js("""
var c=document.querySelector('.virtual-table-container');if(!c)return;
var cbs=c.querySelectorAll('input[type="checkbox"]');
cbs.forEach(function(cb){if(cb.offsetParent!==null&&!cb.checked){cb.click();return;}});
""")
    time.sleep(1)
    
    # 点认领
    claim_btns = page.run_js("""
return(function(){var btns=document.querySelectorAll('button');var r=[];
btns.forEach(function(b){var t=b.textContent.trim();
if(t.indexOf('认领')>-1){var rect=b.getBoundingClientRect();
if(rect.width>10&&rect.height>10)r.push({x:rect.left+rect.width/2,y:rect.top+rect.height/2});}});
return JSON.stringify(r);})()
""")
    claim_btns = json.loads(claim_btns) if claim_btns else []
    if claim_btns:
        b = claim_btns[0]
        page.run_js(f"document.elementFromPoint({b['x']:.0f},{b['y']:.0f}).click()")
        time.sleep(3)
    
    # 提取店铺列表
    stores = page.run_js("""
return(function(){
    var dialogs=document.querySelectorAll('[class*="dialog"]');
    for(var i=0;i<dialogs.length;i++){
        var d=dialogs[i];
        if(d.offsetParent!==null&&getComputedStyle(d).display!=='none'){
            var labels=d.querySelectorAll('[class*="checkbox-group"] label,[class*="t-checkbox"] label');
            var r=[];
            labels.forEach(function(l){var t=l.textContent.trim();if(t&&t!=='全部'&&t.length<50)r.push(t);});
            if(r.length>0)return JSON.stringify(r);
            var blocks=d.querySelectorAll('[class*="select-block"]');
            blocks.forEach(function(b){var t=b.textContent.trim();if(t&&t!=='全部')r.push(t);});
            if(r.length>0)return JSON.stringify(r);
        }
    }
    return JSON.stringify([]);
})()
""")
    stores = json.loads(stores) if stores else []
    print(f"  可用店铺 ({len(stores)}):")
    for i, s in enumerate(stores):
        print(f"    [{i+1}] {s}")
    
    selected_store = None
    if target_store:
        # 🔑 自动匹配：查找包含 target_store 的店铺
        matches = [s for s in stores if target_store in s or s in target_store]
        if matches:
            selected_store = matches[0]
            print(f"\n  ✅ 自动匹配目标店铺: {selected_store}")
        else:
            print(f"\n  ⚠️ 未找到'{target_store}'，可用: {stores}")
    
    if not selected_store and stores:
        print(f"\n  ⚠️ 请选择目标店铺（输入编号或店名）")
        print(f"  🚨 红线：Agent不得自行决策，必须用户确认！")
        return 0  # 等待用户选择后继续
    
    if selected_store:
        # 在弹窗中点击目标店铺
        page.run_js(f"""
var dialogs=document.querySelectorAll('[class*=\"dialog\"]');
for(var i=0;i<dialogs.length;i++){{
    var d=dialogs[i];
    if(!d.offsetParent||getComputedStyle(d).display==='none')continue;
    var labels=d.querySelectorAll('label');
    for(var j=0;j<labels.length;j++){{
        if(labels[j].textContent.includes('{selected_store}')){{
            labels[j].click();break;
        }}
    }}
    // TDesign checkbox-group input
    var cbs=d.querySelectorAll('[class*=\"checkbox-group\"] input,[class*=\"t-checkbox\"] input');
    for(var k=0;k<cbs.length;k++){{
        var cb=cbs[k],parent=cb.parentElement||cb;
        if(parent.textContent.includes('{selected_store}')){{cb.click();break;}}
    }}
}}
""")
        time.sleep(1)
        # 点确认
        confirm = page.run_js("""
var dialogs=document.querySelectorAll('[class*=\"dialog\"]');
for(var i=0;i<dialogs.length;i++){
    var d=dialogs[i];
    if(!d.offsetParent||getComputedStyle(d).display==='none')continue;
    var btns=d.querySelectorAll('button');
    for(var j=0;j<btns.length;j++){
        if(btns[j].textContent.trim()==='确认'||btns[j].textContent.trim()==='确定'){
            btns[j].click();return 'clicked';
        }
    }
}
return 'not_found';
""")
        print(f"  认领确认: {confirm}")
        time.sleep(3)
        print(f"  ✅ 已认领到 {selected_store}")
    
    if not stores:
        print("  ❌ 未找到店铺列表")
        return 1
    
    # ⚠️ 浏览器保持运行，不quit


if __name__ == "__main__":
    sys.exit(main())
