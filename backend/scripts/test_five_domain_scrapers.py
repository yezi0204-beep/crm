"""测试五大能力域抓取器与评分逻辑（不经过 HTTP，直接调用函数）。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes.leads import (
    _fetch_html, _scrape_bidding, _scrape_ecommerce, _scrape_b2b,
    _scrape_competitor, _scrape_forum, _ecommerce_score,
    _evaluate_lead, _detect_industry, _parse_config
)

print('========== 五大能力域抓取器测试 ==========\n')

# 1. 测试 _detect_industry
print('【1】行业自动识别 _detect_industry')
cases = [
    ('卫星通信终端采购项目', '卫星通信'),
    ('高分辨率遥感影像数据采购', '卫星遥感'),
    ('AI智能体开发服务采购', 'AI智能体'),
    ('武器装备配套采购项目', '军工装备'),
    ('信息化系统建设需求', '信息技术'),
]
for text, expected in cases:
    got = _detect_industry(text)
    ok = '✓' if got == expected else '✗'
    print('  {} "{}" -> {} (期望 {})'.format(ok, text[:20], got, expected))

# 2. 测试 _ecommerce_score（高需求低竞争评分）
print('\n【2】电商爆款评分 _ecommerce_score')
ec_cases = [
    (5, 500, '$199.99', 'Top10+低竞争蓝海+中客单价'),
    (25, 2000, '$99', 'Top30+中等竞争'),
    (45, 8000, '$29', 'Top50+高竞争+低客单价'),
]
for rank, rc, price, desc in ec_cases:
    score, reason = _ecommerce_score(rank, rc, price)
    print('  排名#{} 评价{} 价格{} -> 分{} | {} ({})'.format(rank, rc, price, score, reason, desc))

# 3. 测试 _scrape_bidding（招投标 HTML 解析）
print('\n【3】招投标监控 HTML 解析 _scrape_bidding')
bidding_html = '''
<html><body>
<div class="list">
  <a href="/notice/123.html">卫星遥感数据采购项目公告</a>
  <a href="/notice/124.html">VSAT卫星通信终端设备采购需求</a>
  <a href="/login">登录</a>
  <a href="/notice/125.html">AI智能体平台建设招标公告</a>
  <a href="javascript:void(0)">更多</a>
</div></body></html>
'''
source = {'url': 'http://example.com/bids', 'region': '全国', 'name': '测试招标网'}
leads = _scrape_bidding(bidding_html, source, {'max_items': 10}, ['卫星', '通信', '智能体'])
print('  抓取到 {} 条招投标线索'.format(len(leads)))
for l in leads:
    print('    - {} | link:{} | industry:{}'.format(l['opportunity_name'][:30], l['link'][:40], l['industry']))

# 4. 测试 _scrape_ecommerce（电商榜单 HTML 解析）
print('\n【4】电商商机 HTML 解析 _scrape_ecommerce')
ecommerce_html = '''
<html><body>
<div class="zg-item">
  <a href="/dp/B08XYZ123">卫星通信便携终端 V2 双向卫星电话</a>
  <span class="price">$1,299.00</span>
  <span class="rating">1,234 ratings</span>
</div>
<div class="zg-item">
  <a href="/dp/B09ABC456">遥感数据接收处理设备</a>
  <span class="price">$899.00</span>
  <span class="rating">567 ratings</span>
</div>
</body></html>
'''
source_ec = {'name': '亚马逊热销榜', 'region': '海外'}
leads_ec = _scrape_ecommerce(ecommerce_html, source_ec, {'max_items': 5}, ['卫星', '遥感'], 'https://www.amazon.com/Best-Sellers')
print('  抓取到 {} 条电商线索'.format(len(leads_ec)))
for l in leads_ec:
    print('    - {} | industry:{}'.format(l['opportunity_name'][:40], l['industry']))
    raw = _parse_config(l['raw_data'])
    print('      爆款评分:{} 原因:{}'.format(raw.get('ecommerce_score'), raw.get('reason', '')[:50]))

# 5. 测试 _scrape_b2b（企业客源 HTML 解析）
print('\n【5】企业客源 HTML 解析 _scrape_b2b')
b2b_html = '''
<html><body>
<table>
  <tr><td>航天宏图信息技术有限公司</td><td>法定代表人：王宇翔</td><td>成立日期：2020-05-15</td><td>联系电话：010-88888888</td></tr>
  <tr><td>中科卫星通信科技有限公司</td><td>法定代表人：李明</td><td>成立日期：2021-03-20</td></tr>
</table></body></html>
'''
source_b2b = {'url': 'https://www.gsxt.gov.cn/', 'region': '全国', 'name': '企业信用公示'}
leads_b2b = _scrape_b2b(b2b_html, source_b2b, {'max_items': 10}, ['卫星', '航天'], 'https://www.gsxt.gov.cn/')
print('  抓取到 {} 条企业客源线索'.format(len(leads_b2b)))
for l in leads_b2b:
    raw = _parse_config(l['raw_data'])
    print('    - {} | 法人:{} | 成立:{}'.format(l['company'], raw.get('legal_rep', '—'), raw.get('reg_date', '—')))

# 6. 测试 _scrape_competitor（竞品情报 HTML 解析）
print('\n【6】竞品情报 HTML 解析 _scrape_competitor')
competitor_html = '''
<html><body>
<div class="product">
  <a href="/product/sat-phone-1">便携式卫星电话 X1</a>
  <span class="price">价格 ￥5,800</span>
  <span class="promo">限时特价 促销</span>
</div>
<div class="product">
  <a href="/product/vsat-2">VSAT卫星通信站</a>
  <span class="price">价格 ￥128,000</span>
</div>
</body></html>
'''
source_comp = {'name': '竞品A官网', 'region': '全国'}
leads_comp = _scrape_competitor(competitor_html, source_comp, {'max_items': 10}, ['卫星', 'VSAT'], 'https://competitor.com')
print('  抓取到 {} 条竞品情报线索'.format(len(leads_comp)))
for l in leads_comp:
    raw = _parse_config(l['raw_data'])
    promo = raw.get('promo', '')
    print('    - {} | 价格:{} | {}'.format(l['opportunity_name'][:30], raw.get('price', '—'), '促销:'+promo if promo else '常规'))

# 7. 测试 _scrape_forum（舆情痛点 HTML 解析）
print('\n【7】舆情痛点 HTML 解析 _scrape_forum')
forum_html = '''
<html><body>
<div class="post-list">
  <a href="/q/123">现有的遥感数据平台太难用了，经常崩溃报错</a>
  <a href="/q/124">卫星通信终端价格太贵，希望有平价方案</a>
  <a href="/q/125">AI智能体开发需求，采购一套智能客服系统</a>
  <a href="/login">登录</a>
  <a href="/q/126">今天的天气真好</a>
</div></body></html>
'''
source_forum = {'url': 'https://www.zhihu.com/hot', 'region': '全国', 'name': '知乎热榜'}
leads_forum = _scrape_forum(forum_html, source_forum, {'max_items': 10}, ['卫星', '遥感', 'AI'], 'https://www.zhihu.com')
print('  抓取到 {} 条舆情痛点线索'.format(len(leads_forum)))
for l in leads_forum:
    raw = _parse_config(l['raw_data'])
    print('    - {} | 痛点类型:{} 评分:{}'.format(l['opportunity_name'][:35], raw.get('pain_type'), raw.get('sentiment_score')))

# 8. 测试 _evaluate_lead（能力域专属评分）
print('\n【8】能力域专属评估 _evaluate_lead')
industry_stats = {'卫星通信': 5, 'AI智能体': 3, '信息技术': 10}
# 电商商机线索（已有爆款评分）
ec_lead = {'category': '电商商机', 'industry': '卫星通信',
           'raw_data': '{"ecommerce_score": 80, "reason": "Top10+低竞争蓝海"}'}
score, reason = _evaluate_lead(ec_lead, industry_stats)
print('  电商商机线索 -> 分{} | {}'.format(score, reason))
# 舆情痛点线索
forum_lead = {'category': '舆情痛点', 'industry': '信息技术',
              'raw_data': '{"sentiment_score": 76, "pain_type": "需求痛点", "pain_count": 3, "opp_count": 1}'}
score, reason = _evaluate_lead(forum_lead, industry_stats)
print('  舆情痛点线索 -> 分{} | {}'.format(score, reason))
# 竞品情报线索（有促销）
comp_lead = {'category': '竞品情报', 'industry': '卫星通信',
             'raw_data': '{"promo": "限时特价", "price": "5800"}'}
score, reason = _evaluate_lead(comp_lead, industry_stats)
print('  竞品情报线索(促销) -> 分{} | {}'.format(score, reason))
# 企业客源线索
b2b_lead = {'category': '企业客源', 'industry': 'AI智能体', 'raw_data': '{}'}
score, reason = _evaluate_lead(b2b_lead, industry_stats)
print('  企业客源线索 -> 分{} | {}'.format(score, reason))
# 招投标线索（默认评分）
bid_lead = {'category': '招投标监控', 'industry': '卫星通信', 'source': '招投标监控',
            'remark': '卫星遥感数据采购项目，急需招标', 'raw_data': '{}'}
score, reason = _evaluate_lead(bid_lead, industry_stats)
print('  招投标监控线索 -> 分{} | {}'.format(score, reason))

# 9. 测试 _fetch_html（真实网络抓取，可能因网络不可用返回空）
print('\n【9】HTML 抓取 _fetch_html（真实网络）')
html, err = _fetch_html('https://www.baidu.com', dynamic=False, timeout=8)
if html:
    print('  ✓ 百度首页抓取成功，HTML长度: {}'.format(len(html)))
else:
    print('  抓取失败: {}（网络不可用属正常降级）'.format(err))

print('\n========== 测试完成 ==========')
