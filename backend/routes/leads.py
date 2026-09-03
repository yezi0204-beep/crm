"""智能线索管理模块

实现"自动外网抓取多渠道线索 → AI 评估意向 → 精准分配"全流程，覆盖五大能力域：
1. 招投标与政企采购监控——RSS 抓取全国/省市招投标网站，关键词筛选标讯
2. 跨境与国内电商商机——HTML 抓取电商榜单/热搜，分析"高需求低竞争"爆款
3. 精准 B2B 客源提取——HTML 抓取企业信用公示/黄页，批量提取新注册企业
4. 竞争对手情报监听——HTML 监控竞品官网价格/新品/促销变动
5. 行业痛点与舆情分析——HTML 抓取垂直论坛/社区吐槽，挖掘未满足需求

抓取引擎：
- source_type=rss → _scrape_rss（xml.etree 解析）
- source_type=api → _scrape_api（JSON 接口）
- source_type=html → 按 category 分发到 _scrape_bidding/_scrape_ecommerce/
                     _scrape_b2b/_scrape_competitor/_scrape_forum
- source_type=sample → _scrape_sample（仅手动测试）
- source_type=manual → 不自动抓取
- _fetch_html 统一抓取：static requests + 可选 playwright 动态渲染（缺失时降级返回空）

线索队列（scraped_leads）：status 流转 pending→evaluated→imported（拒绝即删除，不再有 rejected 状态）
AI 评估：复用 ai_agent._evaluate_lead_intent 规则评分；电商/竞品/舆情有专属评分
精准分配：_assign_lead 多维度评分推荐负责人——综合销售人员的历史拜访案例、商机推进
         情况、合同签订业绩，按行业匹配/历史业绩/商机转化/拜访经验/工作量6个维度
         打分（满分100），分配即创建客户

权限模型：线索源管理与抓取仅主任/院长；线索查看全员（按分配/状态/类别筛选）。
"""
import json
import random
import re
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
import requests as http_requests
from flask import request, jsonify

from extensions import get_db, token_required, record_operation_log

from . import leads_bp


# ==================== 线索源 CRUD ====================

# ==================== 线索源管理已迁移至 /api/data-sources ====================
# 说明：数据源 CRUD + 采集器插件管理 + 手动采集已统一至 routes/data_sources.py，
# 操作同一张 lead_sources 表，权限改为 RBAC（system.admin / data.view_all）。
# 旧 /api/leads/sources 接口已删除，前端请调用 /api/data-sources。


# ==================== 抓取引擎 ====================
# 说明：网络抓取入口已统一至 AI情报中心-原始情报库（/intelligence/collect），
# 采集结果经业务关键词过滤后存入 raw_intelligence，再由 AI商机识别分析转入本页线索队列。
# 此处仅保留数据源 CRUD 与手动导入，避免双链路重复抓取同一批 lead_sources。


# ==================== AI 智能体互联网搜索（核心能力）====================

# 搜索引擎会话（复用 cookie 降低限速概率）
_search_session = None
_UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]


def _get_search_session():
    """获取/复用 requests.Session（带 cookie），降低搜索引擎限速概率。"""
    global _search_session
    if _search_session is None:
        _search_session = http_requests.Session()
        _search_session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
    return _search_session


def _search_web(query, max_results=15):
    """搜索互联网，返回真实搜索结果。多引擎降级：DuckDuckGo POST → Bing 移动版。

    返回 [{title, url, snippet}, ...]。网络不可用或无结果时返回空列表，绝不造假数据。
    """
    if not query:
        return []
    # 1) 优先 DuckDuckGo（POST 方式，降低限速概率）
    results = _search_duckduckgo(query, max_results)
    if results:
        return results
    # 2) DuckDuckGo 限速/无结果，降级 Bing 移动版（返回静态 HTML，无需 JS）
    return _search_bing(query, max_results)


def _search_duckduckgo(query, max_results=15):
    """DuckDuckGo HTML 搜索（POST 方式 + Session cookie），解码重定向链接获取真实 URL。"""
    try:
        session = _get_search_session()
        ua = random.choice(_UA_POOL)
        # POST 方式比 GET 更不容易被限速
        resp = session.post(
            'https://html.duckduckgo.com/html/',
            data={'q': query, 'b': '', 'kl': 'cn-zh'},
            headers={'User-Agent': ua},
            timeout=12,
        )
        if resp.status_code != 200 or not resp.text:
            return []
        html = resp.text
        # 限速检测：DuckDuckGo 限速时返回 202 或异常页面
        if resp.status_code == 202 or 'anomaly' in html.lower()[:500]:
            print('[_search_duckduckgo] 检测到限速，将降级到 Bing')
            return []
        results = []
        link_pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )
        snippet_pattern = re.compile(
            r'class="result__snippet"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )
        from urllib.parse import unquote, urlparse, parse_qs
        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)
        for i, (raw_link, raw_title) in enumerate(links):
            url = raw_link
            if 'uddg=' in raw_link:
                try:
                    if raw_link.startswith('//'):
                        raw_link = 'https:' + raw_link
                    parsed = urlparse(raw_link)
                    qs = parse_qs(parsed.query)
                    if 'uddg' in qs:
                        url = unquote(qs['uddg'][0])
                except Exception:
                    url = raw_link
            title = re.sub(r'<[^>]+>', '', raw_title).strip()
            title = re.sub(r'\s+', ' ', title)
            if not title or len(title) < 4:
                continue
            snippet = ''
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
                snippet = re.sub(r'\s+', ' ', snippet)
            results.append({'title': title, 'url': url, 'snippet': snippet})
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        print(f'[_search_duckduckgo] 失败: {e}')
        return []


def _search_bing(query, max_results=15):
    """Bing 搜索兜底（DuckDuckGo 限速时使用）。

    Bing 直连（不用代理）可返回含 b_algo 结果块的静态 HTML。
    从 b_algo 块中提取 <h2><a href="URL">标题</a></h2> 和 <p>摘要</p>。
    """
    try:
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        resp = http_requests.get(
            'https://cn.bing.com/search',
            params={'q': query, 'count': max_results},
            headers={'User-Agent': ua, 'Accept-Language': 'zh-CN,zh;q=0.9'},
            timeout=12,
            proxies={'http': None, 'https': None},  # Bing 直连不走代理
        )
        if resp.status_code != 200 or not resp.text:
            return []
        html = resp.text
        results = []
        # 提取 b_algo 结果块
        item_pattern = re.compile(
            r'<li[^>]*class="b_algo"[^>]*>(.*?)</li>',
            re.IGNORECASE | re.DOTALL
        )
        for block in item_pattern.findall(html):
            # 标题链接在 <h2><a href="URL">标题</a></h2>
            # 先定位 h2 标签，再从中提取链接和标题（避免捕获 cite/domain 噪声）
            h2_m = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.IGNORECASE | re.DOTALL)
            link_m = None
            if h2_m:
                link_m = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', h2_m.group(1), re.IGNORECASE | re.DOTALL)
            if not link_m:
                # 兜底：直接从 block 中找第一个外部链接
                link_m = re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, re.IGNORECASE | re.DOTALL)
            if not link_m:
                continue
            url = link_m.group(1)
            # 排除 Bing 内部链接
            if any(d in url for d in ['bing.com', 'microsoft.com', 'go.microsoft']):
                continue
            title = re.sub(r'<[^>]+>', '', link_m.group(2)).strip()
            title = re.sub(r'\s+', ' ', title)
            # 清理标题中的域名前缀噪声（如 "baidu.comhttps://..."）
            title = re.sub(r'^[a-z0-9.-]+\.(com|cn|org|net|gov|edu)[a-z0-9/:.-]*\s*', '', title, flags=re.IGNORECASE)
            if not title or len(title) < 4:
                continue
            # 摘要在 <p> 或 <div class="b_caption"> 中
            snippet_m = re.search(r'<p[^>]*>(.*?)</p>', block, re.IGNORECASE | re.DOTALL)
            snippet = ''
            if snippet_m:
                snippet = re.sub(r'<[^>]+>', '', snippet_m.group(1)).strip()
                snippet = re.sub(r'\s+', ' ', snippet)
                # 清理 HTML 实体
                snippet = snippet.replace('&ensp;', ' ').replace('&#0183;', '·').replace('&nbsp;', ' ')
            results.append({'title': title, 'url': url, 'snippet': snippet})
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        print(f'[_search_bing] 失败: {e}')
        return []


# 五大能力域搜索查询模板（{kw} = 关键词，{year} = 当前年份）
_CATEGORY_SEARCH_TEMPLATES = {
    '招投标监控': '{kw} 采购 招标 公告 {year}',
    '电商商机': '{kw} 热销 排行榜 价格 销量',
    '企业客源': '{kw} 公司 新注册 企业 黄页',
    '竞品情报': '{kw} 竞品 价格 促销 新品',
    '舆情痛点': '{kw} 吐槽 问题 需求 难用',
}

# 招投标监控：真实政企采购/招投标网站域名（site: 定向搜索，确保结果为真实公告）
_BIDDING_SITES = [
    'ccgp.gov.cn',          # 中国政府采购网
    'chinabidding.com.cn',  # 中国招标与采购网
    'ggzy.gov.cn',           # 全国公共资源交易平台
    'cebpubservice.com',     # 中国招标投标公共服务平台
    'bidcenter.com.cn',      # 中国采招网
]

# 军采监控：军队采购/武器装备采购网站域名
_MILITARY_SITES = [
    'plap.cn',               # 全军武器装备采购信息网
    'weain.mil.cn',           # 军队采购网
    'ccgp.gov.cn',            # 中国政府采购网（含军采板块）
    'ein.mil.cn',             # 军队物资采购网
]

# 军工企业9大业务领域关键词（用户明确关注：采购站/装备健康/模拟器/雷达/卫通/智能体/仿真/软件/卫星/靶场/对抗）
# 用于搜索查询构建 + 领域匹配加分 + 行业识别
MILITARY_DOMAIN_KEYWORDS = {
    '装备健康': ['装备健康', '健康管理', 'PHM', '状态监测', '故障预测', '维修保障', '装备保障', '预测性维护'],
    '模拟器': ['模拟器', '训练模拟器', '虚拟训练', '模拟训练', '驾驶模拟器', '操作模拟器'],
    '雷达': ['雷达', '相控阵', '合成孔径', '雷达系统', '雷达探测', '毫米波雷达', '机载雷达'],
    '卫通': ['卫通', '卫星通信', '通信终端', 'VSAT', '卫星终端', '卫星电话', '动中通', '卫星通信终端'],
    '智能体': ['智能体', '人工智能', '大模型', 'AI', 'AIGC', '智能决策', 'AI开发'],
    '仿真': ['仿真', '半实物仿真', '虚拟仿真', '作战仿真', '仿真系统', '仿真平台', '仿真测试'],
    '软件': ['软件', '信息系统', '信息化', '软件定制', '指挥控制', 'C4ISR', '软件研发'],
    '卫星': ['卫星', '遥感', '遥感数据', '遥感影像', '卫星遥感', '卫星导航', '北斗', '卫星终端'],
    '靶场': ['靶场', '试验场', '武器试验', '作战试验', '试验鉴定', '靶标', '外场试验'],
    '对抗': ['对抗', '电子战', '电子对抗', '电磁对抗', '干扰机', '电磁干扰', '雷达对抗', '电磁脉冲'],
}

# 军采链接白名单（这些域名的链接优先级最高，是真实军采公告）
_MILITARY_WHITELIST = {
    'plap.cn', 'weain.mil.cn', 'ein.mil.cn', 'ccgp.gov.cn',
    'ggzy.gov.cn', 'cebpubservice.com', 'chinabidding.com.cn', 'bidcenter.com.cn',
}

# 非商机网站黑名单（百科/词典/问答/新闻/地图/导航/文档库/社交等通用页面）
# 这些页面绝不是采购公告，必须在抓取阶段直接丢弃
_JUNK_DOMAINS = {
    # 百度系
    'baike.baidu.com', 'baijiahao.baidu.com', 'jingyan.baidu.com',
    'zhidao.baidu.com', 'wenku.baidu.com', 'tieba.baidu.com',
    'map.baidu.com', 'ditu.baidu.com', 'news.baidu.com', 'cp.baidu.com',
    # 知乎/豆瓣/微博/微信
    'zhihu.com', 'douban.com', 'weibo.com', 'mp.weixin.qq.com',
    # 搜狗百科/360百科
    'baike.sogou.com', 'baike.so.com',
    # 维基/镜像
    'wikipedia.org', 'wikiwand.com',
    # 新闻门户（非政府采购公告）
    'news.sina.com.cn', 'news.sohu.com', 'news.163.com', 'news.qq.com',
    '163.com', 'sina.com.cn', 'sohu.com', 'qq.com', 'toutiao.com',
    # 文档库
    'docin.com', 'doc88.com',
    # 地图
    'map.bmcx.com', 'earthol.com', '17ditu.com', 'bajiu.cn', 'earth.google.com',
    # 设计/图片
    'zcool.com.cn', 'huaban.com', 'pixiv.net',
    # 词典/翻译/国学/古籍（"人工""装备""武器"等词被搜索到词典解释）
    'iciba.com', 'chazidian.com', 'gushici.net', 'hgcha.com',
    'hanyuguoxue.com', 'shidianguji.com', 'hanziguoxue.com',
    'dict.revised.moe.edu.tw', 'zidian.gushici.net',
    # 百科类
    'huoqibaike.club',
    # 本地宝/生活
    'bendibao.com',
    # 军事资讯（非采购公告）
    'military.china.com.cn',
}


def _is_junk_url(url):
    """判断 URL 是否为非商机通用页面（百科/词典/问答/新闻/地图等）。"""
    if not url:
        return True
    url_lower = url.lower()
    return any(d in url_lower for d in _JUNK_DOMAINS)


# 严重垃圾域名（绝对不可能包含商机信息）
_SEVERE_JUNK_DOMAINS = {
    # 百度百科/百度知道/百度文库
    'baike.baidu.com', 'zhidao.baidu.com', 'wenku.baidu.com',
    # 知乎/豆瓣/微博
    'zhihu.com', 'douban.com', 'weibo.com',
    # 维基
    'wikipedia.org', 'wikiwand.com',
    # 词典/国学
    'iciba.com', 'chazidian.com', 'gushici.net',
    # 地图
    'map.bmcx.com', 'earthol.com', '17ditu.com',
    # 设计/图片
    'zcool.com.cn', 'huaban.com',
}


def _is_severe_junk_url(url):
    """判断 URL 是否为极端垃圾页面（不可能包含任何商机信息）。"""
    if not url:
        return True
    url_lower = url.lower()
    return any(d in url_lower for d in _SEVERE_JUNK_DOMAINS)


# 采购意图关键词——军采监控降级路径必须命中至少一个才保留
_PROCUREMENT_KEYWORDS = [
    '招标', '采购', '公告', '中标', '成交', '询价', '谈判', '公示',
    '需求公示', '意向公告', '竞争性', '单一来源', '投标', '开标',
    'procurement', 'tender', 'bid',
]


def _has_procurement_intent(text):
    """判断文本是否包含采购意图关键词（用于降级路径军采监控过滤）。"""
    if not text:
        return False
    return any(k in text for k in _PROCUREMENT_KEYWORDS)


def _build_search_queries(keywords, category, max_queries=3):
    """根据关键词和能力域构建搜索查询列表。

    招投标监控：用 site: 定向搜索真实政企采购网站，确保结果为招标公告而非百科/地图。
    军采监控：用 site: 定向搜索军队采购/武器装备采购网站。
    其他能力域：用 category 模板包装关键词。
    """
    from datetime import datetime
    year = str(datetime.now().year)

    if category == '招投标监控':
        # site: 定向搜索：每个关键词搭配一个招投标网站，确保返回真实公告
        if not keywords:
            keywords = ['采购', '招标', '中标']
        queries = []
        for i, kw in enumerate(keywords[:max_queries]):
            site = _BIDDING_SITES[i % len(_BIDDING_SITES)]
            queries.append('{} 招标 采购 {} site:{}'.format(kw, year, site))
        return queries

    if category == '军采监控':
        # 分层搜索策略：军采网站（plap.cn/weain.mil.cn）搜索引擎索引差，
        # site: 定向常返回空，故以通用军采搜索为主（占50%），辅以 site: 定向和装备采购搜索
        # 每个查询覆盖用户9大业务领域之一，确保全面覆盖
        if not keywords:
            # 默认覆盖用户9大业务领域核心词
            keywords = ['装备健康', '模拟器', '雷达', '卫通', '智能体',
                        '仿真', '软件', '卫星', '靶场', '对抗']
        queries = []
        for i, kw in enumerate(keywords[:max_queries]):
            if i % 4 == 0:
                # 通用军采搜索（覆盖 ccgp.gov.cn / weain.mil.cn / 各类军采渠道）
                queries.append('{kw} 军队 采购 招标 公告 {year}'.format(kw=kw, year=year))
            elif i % 4 == 1:
                # 装备采购搜索（针对武器装备类，覆盖装备发展部渠道）
                queries.append('{kw} 装备采购 武器装备 采购公告 {year}'.format(kw=kw, year=year))
            elif i % 4 == 2:
                # site: 定向 plap.cn（全军武器装备采购信息网）
                queries.append('{kw} 采购 招标 {year} site:plap.cn'.format(kw=kw, year=year))
            else:
                # site: 定向 ccgp.gov.cn（中国政府采购网，含军采板块）
                queries.append('{kw} 军用 采购 {year} site:ccgp.gov.cn'.format(kw=kw, year=year))
        return queries

    # 其他能力域用模板
    template = _CATEGORY_SEARCH_TEMPLATES.get(category, '{kw} {year}')
    if not keywords:
        return [template.format(kw=category or '商机', year=year)]
    return [template.format(kw=kw, year=year) for kw in keywords[:max_queries]]


def _scrape_ai_search(source, config, keywords, category):
    """AI 智能体互联网搜索抓取：搜索 → 预过滤 → LLM 结构化提取 → 后过滤。

    全链路：
    1. 根据 category + keywords 构建搜索查询
    2. _search_web 搜索 DuckDuckGo/Bing 获取真实结果（最多 20 条）
    3. 预过滤：排除百科/词典/社交等垃圾域名
    4. LLM 提取结构化商机线索（关闭思考模式，60 秒超时）
    5. LLM 失败时降级为关键词匹配提取
    6. 后过滤：丢弃 LLM 返回的垃圾链接，去重
    """
    max_items = config.get('max_items', 15)
    max_queries = config.get('max_queries', 3)
    queries = _build_search_queries(keywords, category, max_queries)

    # 搜索阶段：每个查询取 max_items 条，合并去重
    all_results = []
    seen_urls = set()
    for idx, q in enumerate(queries):
        results = _search_web(q, max_results=max_items)
        for r in results:
            url = r.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)
        if len(all_results) >= max_items * 2:
            break
        if idx < len(queries) - 1:
            time.sleep(2)

    if not all_results:
        print('[_scrape_ai_search] 搜索无结果')
        return []

    # 预过滤：排除垃圾域名
    all_results = [r for r in all_results if not _is_junk_url(r.get('url', ''))]
    if not all_results:
        print('[_scrape_ai_search] 预过滤后无结果')
        return []

    # LLM 提取
    leads = _llm_extract_leads(all_results, keywords, category, max_items)
    if leads is not None:
        # 后过滤：去重（按链接）
        seen_lead_urls = set()
        deduped = []
        for lead in leads:
            url = lead.get('link', '')
            if url in seen_lead_urls:
                continue
            seen_lead_urls.add(url)
            deduped.append(lead)
        print(f'[_scrape_ai_search] LLM 提取 {len(leads)} 条，去重后 {len(deduped)} 条')
        return deduped

    # LLM 失败：降级提取
    print('[_scrape_ai_search] LLM 不可用，降级为关键词提取')
    return _fallback_extract_leads(all_results, source, keywords, category, max_items)


def _llm_extract_leads(search_results, keywords, category, max_items):
    """用 LLM 从搜索结果中提取结构化商机线索。LLM 不可用时返回 None。

    优化：关闭思考模式 + 短 prompt + 60 秒超时，避免长时间等待。
    """
    try:
        from qa_engine import call_llm
    except Exception:
        return None
    # 最多传 8 条给 LLM，每条限制长度，减少 token 消耗
    llm_items = min(len(search_results), 8)
    results_text = '\n'.join(
        '{}. {} | {} | {}'.format(
            i + 1,
            r['title'][:60],
            r['url'][:80],
            r.get('snippet', '')[:80]
        )
        for i, r in enumerate(search_results[:llm_items])
    )
    kw_str = '、'.join(keywords) if keywords else '不限'

    # 统一 prompt（不再区分军采/通用，LLM 能理解 category）
    prompt = (
        '从以下搜索结果中提取商机线索，只返回JSON数组。\n'
        '类别: {cat} | 关键词: {kw}\n\n'
        '搜索结果:\n{results}\n\n'
        '规则: 只提取采购/招标/需求类商机，排除百科/新闻/问答/社交。\n'
        '无商机则返回 []。每条含: company(采购方), opportunity_name(项目名), '
        'link(原样复制URL), industry(行业), region(地区), intent(一句话描述), '
        'intent_score(0-100), publish_date, deadline, budget, procurement_method, '
        'contact_name, phone。无则空字符串。'
    ).format(cat=category or '商机', kw=kw_str, results=results_text)

    messages = [
        {'role': 'system', 'content': '你是商机线索分析助手，只返回JSON数组，不要任何其他文字。'},
        {'role': 'user', 'content': prompt}
    ]
    # 关闭思考模式，60 秒超时，18000 token 足够
    raw = call_llm(messages, max_tokens=18000, timeout=360, enable_thinking=False)
    if not raw:
        return None
    # 解析 LLM 返回的 JSON
    items = None
    try:
        raw = raw.strip()
        # 尝试 markdown 代码块
        m = re.search(r'```(?:json)?\s*\n?(.*?)```', raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
        else:
            start = raw.find('[')
            end = raw.rfind(']')
            if start >= 0 and end > start:
                raw = raw[start:end + 1]
        items = json.loads(raw)
    except Exception as e:
        print(f'[_llm_extract_leads] JSON 解析失败: {e}, raw[:200]={raw[:200]}')
        return None

    leads = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        title = (item.get('opportunity_name') or item.get('company') or '').strip()
        if not title:
            continue
        link = (item.get('link') or '').strip()
        # 用搜索结果中的真实链接匹配验证
        matched_url = ''
        for sr in search_results:
            if link and link in sr['url']:
                matched_url = sr['url']
                break
            if link and sr['url'] in link:
                matched_url = sr['url']
                break
        if matched_url:
            link = matched_url
        # 后过滤：丢弃垃圾链接
        if _is_junk_url(link):
            continue
        industry = item.get('industry') or _detect_industry(title)
        contact_name = (item.get('contact_name') or '').strip()
        phone = (item.get('phone') or '').strip()
        region = (item.get('region') or '全国').strip() or '全国'
        publish_date = (item.get('publish_date') or '').strip()
        deadline = (item.get('deadline') or '').strip()
        budget = (item.get('budget') or '').strip()
        procurement_method = (item.get('procurement_method') or '').strip()
        intent = (item.get('intent') or '').strip()
        remark_parts = [intent]
        if procurement_method:
            remark_parts.append(f'采购方式:{procurement_method}')
        if budget:
            remark_parts.append(f'预算:{budget}')
        if deadline:
            remark_parts.append(f'截止:{deadline}')
        elif publish_date:
            remark_parts.append(f'发布:{publish_date}')
        remark = '；'.join(p for p in remark_parts if p)[:200]
        leads.append({
            'company': (item.get('company') or title[:30]).strip(),
            'opportunity_name': title,
            'contact_name': contact_name, 'phone': phone, 'email': '',
            'industry': industry,
            'region': region,
            'source': 'AI智能体搜索',
            'link': link,
            'remark': remark,
            'publish_date': publish_date,
            'deadline': deadline,
            'budget': budget,
            'procurement_method': procurement_method,
            'raw_data': json.dumps({
                'title': title, 'link': link, 'industry': industry,
                'intent': intent, 'intent_score': item.get('intent_score', 50),
                'contact_name': contact_name, 'phone': phone, 'region': region,
                'publish_date': publish_date, 'deadline': deadline,
                'budget': budget, 'procurement_method': procurement_method,
                'category': category or '商机', 'source_type': 'ai_search', 'llm_used': True,
                'snippet': next((sr.get('snippet', '') for sr in search_results if sr['url'] == link), '')
            }, ensure_ascii=False),
            'category': category or '',
        })
    return leads


def _fallback_extract_leads(search_results, source, keywords, category, max_items):
    """LLM 不可用时的降级提取：直接用搜索结果标题/链接/摘要作为线索。

    关键词过滤采用宽松匹配：复合关键词（如"卫星遥感"）拆分为单字/词组，
    命中任一即保留；若过滤后无结果则返回全部（搜索引擎已按查询词筛选）。
    """
    # 将复合关键词拆分为更细粒度的匹配词（如"卫星遥感"→"卫星"+"遥感"）
    match_terms = set()
    for kw in keywords:
        match_terms.add(kw)
        # 拆分2字以上的复合词为2字子串
        if len(kw) >= 4:
            for i in range(0, len(kw) - 1, 2):
                match_terms.add(kw[i:i + 2])

    leads = []
    for r in search_results[:max_items]:
        # 降级路径也过滤百科/词典/问答/新闻等非商机页面
        if _is_junk_url(r.get('url', '')):
            continue
        title = r['title']
        snippet = r.get('snippet', '')
        text = title + ' ' + snippet
        # 军采监控降级路径：必须命中采购意图关键词，否则丢弃
        # （降级路径无法像LLM那样理解语义，只能靠关键词硬过滤）
        if category == '军采监控':
            if not _has_procurement_intent(text):
                continue
        # 其他类别：过滤明显非商机的词典/百科类标题
        junk_title_patterns = ['是什么意思', '怎么读', '念什么', '拼音', '近义词',
                               '反义词', '翻译', '读音', '释义', '解释', '百科',
                               '_百度知道', '- 知乎', '是什么', '如何定义']
        if any(p in title for p in junk_title_patterns):
            continue
        # 关键词匹配：命中任一关键词（或拆分后的词组）才保留
        if match_terms and not any(term in text for term in match_terms):
            continue
        lead = {
            'company': _extract_company(title) or title[:30],
            'opportunity_name': title,
            'contact_name': '', 'phone': '', 'email': '',
            'industry': _detect_industry(text),
            'region': source.get('region', '全国'),
            'source': 'AI智能体搜索',
            'link': r['url'],
            'remark': snippet[:120] if snippet else title[:100],
            'publish_date': '', 'deadline': '', 'budget': '', 'procurement_method': '',
            'raw_data': json.dumps({
                'title': title, 'link': r['url'], 'snippet': snippet[:200],
                'category': category or '', 'source_type': 'ai_search', 'llm_used': False
            }, ensure_ascii=False),
            'category': category or '',
        }
        leads.append(lead)
    # 降级路径不再"无结果时返回全部"——无结果说明搜索结果确实没有商机，返回空比返回垃圾好
    return leads


def _scrape_procurement_site(source, config, keywords, category):
    """直接抓取采购网站公告列表页。

    比搜索引擎更有效：直接从 ccgp.gov.cn / plap.cn 等网站提取真实公告。
    工作流程：
    1. HTTP GET 获取公告列表页 HTML
    2. 正则提取所有公告链接（标题含采购/招标/中标/询价/谈判等关键词）
    3. LLM 从公告标题中提取结构化信息 + 按用户关键词过滤
    4. LLM 不可用时降级为关键词匹配
    """
    url = source.get('url', '')
    if not url:
        return []
    max_items = config.get('max_items', 20)

    # 第1步：获取列表页
    try:
        session = _get_search_session()
        resp = session.get(url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })
        if resp.status_code != 200 or not resp.text:
            print(f'[_scrape_procurement_site] HTTP {resp.status_code} for {url}')
            return []
        # 自动检测编码
        resp.encoding = resp.apparent_encoding or 'utf-8'
        html = resp.text
    except Exception as e:
        print(f'[_scrape_procurement_site] 请求失败: {e}')
        return []

    # 第2步：从 HTML 提取公告链接和标题
    # 匹配 <a href="...">标题</a>，标题含采购/招标/中标等关键词
    link_pattern = re.compile(r'href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
    announcements = []
    seen_urls = set()
    procurement_keywords = ['采购', '招标', '中标', '公告', '询价', '谈判', '磋商',
                            '成交', '废标', '更正', '公示', '单一来源']

    for link, raw_title in link_pattern.findall(html):
        title = re.sub(r'<[^>]+>', '', raw_title).strip()
        title = re.sub(r'\s+', ' ', title)
        if not title or len(title) < 8:
            continue
        # 必须含采购类关键词
        if not any(k in title for k in procurement_keywords):
            continue
        # 构建完整 URL
        full_url = _resolve_url(url, link)
        if not full_url or full_url in seen_urls:
            continue
        # 排除非公告链接（CSS/JS/导航等）
        if any(ext in full_url.lower() for ext in ['.css', '.js', '.jpg', '.png', '.ico']):
            continue
        seen_urls.add(full_url)
        # 从 HTML 中尝试提取日期
        date = _extract_date_near(html, link)
        announcements.append({
            'title': title,
            'url': full_url,
            'date': date,
            'snippet': title,  # 列表页没有摘要，用标题代替
        })
        if len(announcements) >= max_items * 2:
            break

    if not announcements:
        print(f'[_scrape_procurement_site] 未从 {url} 提取到公告')
        return []

    print(f'[_scrape_procurement_site] 提取到 {len(announcements)} 条公告')

    # 第3步：LLM 提取结构化线索
    leads = _llm_filter_procurement(announcements, keywords, category, max_items)
    if leads is not None:
        print(f'[_scrape_procurement_site] LLM 过滤后 {len(leads)} 条线索')
        return leads

    # 第4步：LLM 不可用时降级为关键词匹配
    return _fallback_filter_procurement(announcements, keywords, category, max_items)


def _llm_filter_procurement(announcements, keywords, category, max_items):
    """用 LLM 从公告列表中筛选与关键词相关的商机。LLM 不可用时返回 None。"""
    try:
        from qa_engine import call_llm
    except Exception:
        return None
    # 构建公告文本（最多 15 条）
    items_text = '\n'.join(
        '{}. {} | {} | {}'.format(i + 1, a['title'][:60], a['url'][:80], a.get('date', ''))
        for i, a in enumerate(announcements[:15])
    )
    kw_str = '、'.join(keywords) if keywords else '不限'

    prompt = (
        '从以下采购公告中筛选与关键词相关的商机，只返回JSON数组。\n'
        '类别: {cat} | 关键词: {kw}\n\n'
        '公告列表:\n{items}\n\n'
        '规则: 只要公告标题中包含任一关键词或其近义词就保留。'
        '例如关键词"雷达"匹配"雷达/相控阵/微波"，"仿真"匹配"仿真/模拟/虚拟"，'
        '"智能体"匹配"AI/人工智能/智能/大模型"，"卫通"匹配"卫星/通信/卫通"。'
        '不要过于严格，宁可多留也不要漏掉。\n'
        '无相关则返回 []。每条含: company(采购方), opportunity_name(项目名), '
        'link(原样复制URL), industry(行业), intent(一句话描述), '
        'intent_score(0-100), publish_date(日期), procurement_method(采购方式)。'
    ).format(cat=category or '商机', kw=kw_str, items=items_text)

    messages = [
        {'role': 'system', 'content': '你是商机分析助手，只返回JSON数组。'},
        {'role': 'user', 'content': prompt}
    ]
    raw = call_llm(messages, max_tokens=18000, timeout=360, enable_thinking=False)
    if not raw:
        return None
    try:
        raw = raw.strip()
        m = re.search(r'```(?:json)?\s*\n?(.*?)```', raw, re.DOTALL)
        if m:
            raw = m.group(1).strip()
        else:
            start = raw.find('[')
            end = raw.rfind(']')
            if start >= 0 and end > start:
                raw = raw[start:end + 1]
        items = json.loads(raw)
    except Exception as e:
        print(f'[_llm_filter_procurement] JSON 解析失败: {e}')
        return None

    # 用原始公告 URL 验证
    url_map = {a['url']: a for a in announcements}
    leads = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        title = (item.get('opportunity_name') or item.get('company') or '').strip()
        if not title:
            continue
        link = (item.get('link') or '').strip()
        # 验证链接来自原始公告
        matched = None
        for ann in announcements:
            if link and (link in ann['url'] or ann['url'] in link):
                matched = ann
                break
        if matched:
            link = matched['url']
        industry = item.get('industry') or _detect_industry(title)
        publish_date = (item.get('publish_date') or (matched['date'] if matched else '')).strip()
        procurement_method = (item.get('procurement_method') or '').strip()
        intent = (item.get('intent') or '').strip()
        remark_parts = [intent]
        if procurement_method:
            remark_parts.append(f'采购方式:{procurement_method}')
        if publish_date:
            remark_parts.append(f'发布:{publish_date}')
        remark = '；'.join(p for p in remark_parts if p)[:200]
        leads.append({
            'company': (item.get('company') or title[:30]).strip(),
            'opportunity_name': title,
            'contact_name': '', 'phone': '', 'email': '',
            'industry': industry,
            'region': '全国',
            'source': '采购网站抓取',
            'link': link,
            'remark': remark,
            'publish_date': publish_date,
            'deadline': '', 'budget': '',
            'procurement_method': procurement_method,
            'raw_data': json.dumps({
                'title': title, 'link': link, 'industry': industry,
                'intent': intent, 'intent_score': item.get('intent_score', 50),
                'publish_date': publish_date, 'procurement_method': procurement_method,
                'category': category or '商机', 'source_type': 'procurement', 'llm_used': True,
            }, ensure_ascii=False),
            'category': category or '',
        })
    return leads


def _fallback_filter_procurement(announcements, keywords, category, max_items):
    """LLM 不可用时：关键词匹配过滤公告。"""
    match_terms = set()
    for kw in keywords:
        match_terms.add(kw)
        if len(kw) >= 4:
            for i in range(0, len(kw) - 1, 2):
                match_terms.add(kw[i:i + 2])

    leads = []
    for ann in announcements[:max_items]:
        title = ann['title']
        # 关键词匹配
        if match_terms and not any(term in title for term in match_terms):
            continue
        # 从标题提取采购方式
        method = ''
        for m in ['公开招标', '邀请招标', '竞争性谈判', '竞争性磋商', '询价', '单一来源']:
            if m in title:
                method = m
                break
        leads.append({
            'company': _extract_company(title) or title[:30],
            'opportunity_name': title,
            'contact_name': '', 'phone': '', 'email': '',
            'industry': _detect_industry(title),
            'region': '全国',
            'source': '采购网站抓取',
            'link': ann['url'],
            'remark': title[:120],
            'publish_date': ann.get('date', ''),
            'deadline': '', 'budget': '',
            'procurement_method': method,
            'raw_data': json.dumps({
                'title': title, 'link': ann['url'],
                'category': category or '', 'source_type': 'procurement', 'llm_used': False,
            }, ensure_ascii=False),
            'category': category or '',
        })
    return leads


def _resolve_url(base_url, link):
    """将相对 URL 解析为绝对 URL。"""
    from urllib.parse import urljoin
    return urljoin(base_url, link)


def _extract_date_near(html, link_marker):
    """尝试从链接附近的 HTML 中提取日期（YYYY-MM-DD 或 YYYY.MM.DD）。"""
    # 找链接在 HTML 中的位置，取前后 200 字符
    pos = html.find(link_marker)
    if pos < 0:
        return ''
    context = html[max(0, pos - 100):pos + 200]
    date_patterns = [
        r'(\d{4}[-./]\d{1,2}[-./]\d{1,2})',
        r'(\d{4}年\d{1,2}月\d{1,2}日)',
    ]
    for pattern in date_patterns:
        m = re.search(pattern, context)
        if m:
            date = m.group(1)
            # 统一为 YYYY-MM-DD
            date = re.sub(r'[年/.]', '-', date)
            return date
    return ''


def _scrape_source(source):
    """按源类型/类别分发抓取，返回 (leads_list, error_str)。"""
    try:
        stype = source['source_type']
        config = _parse_config(source.get('config'))
        keywords = (source.get('keywords') or '').split(',')
        keywords = [k.strip() for k in keywords if k.strip()]
        industry = source.get('industry', '')
        region = source.get('region', '全国')
        category = source.get('category', '')

        if stype == 'rss':
            return _scrape_rss(source.get('url', ''), keywords, config.get('max_items', 20)), None
        if stype == 'api':
            return _scrape_api(source.get('url', ''), config, keywords, industry, region), None
        if stype == 'html':
            return _scrape_html_by_category(source, config, keywords, category), None
        if stype == 'ai_search':
            return _scrape_ai_search(source, config, keywords, category), None
        if stype == 'procurement':
            return _scrape_procurement_site(source, config, keywords, category), None
        if stype == 'sample':
            return _scrape_sample(config.get('count', 5), keywords, industry, region), None
        if stype == 'manual':
            return [], None
        return [], '不支持的源类型'
    except Exception as e:
        return [], f'抓取异常: {e}'


def _parse_config(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {}


def _detect_industry(text):
    """根据文本关键词自动识别行业（覆盖军工企业关注领域）。

    军工细分：雷达电子/仿真模拟/靶场试验/电子对抗/装备健康/卫通卫星/AI智能体/军工装备/信息技术。
    """
    if not text:
        return '信息技术'
    # 雷达电子优先匹配（避免被通用"电子"误吞）
    if any(k in text for k in ['雷达', '相控阵', '雷达系统', '雷达探测']):
        return '雷达电子'
    # 电子对抗
    if any(k in text for k in ['对抗', '电子战', '电子对抗', '电磁对抗', '电磁干扰', '干扰机']):
        return '电子对抗'
    # 仿真模拟
    if any(k in text for k in ['仿真', '模拟器', '模拟训练', '虚拟训练', '训练模拟', '半实物仿真']):
        return '仿真模拟'
    # 靶场试验
    if any(k in text for k in ['靶场', '试验场', '武器试验', '作战试验', '试验鉴定']):
        return '靶场试验'
    # 装备健康/保障
    if any(k in text for k in ['装备健康', '健康管理', '状态监测', 'PHM', '维修保障', '装备保障', '故障预测']):
        return '装备健康'
    # 卫通卫星（优先于通用"卫星"）
    if any(k in text for k in ['卫通', '卫星通信', '通信终端', 'VSAT', '卫星终端', '卫星电话']):
        return '卫通卫星'
    if any(k in text for k in ['遥感', '遥感数据', '遥感影像', '遥感卫星']):
        return '卫星遥感'
    # AI智能体
    if any(k in text for k in ['智能体', '人工智能', '大模型', 'AI开发', 'AI智能', 'AIGC']):
        return 'AI智能体'
    # 军工装备兜底
    if any(k in text for k in ['装备', '武器', '军用', '军工', '军采', '国防', '部队', '作战']):
        return '军工装备'
    return '信息技术'


def _match_military_domain(text):
    """检测文本命中用户9大业务领域之一，返回领域名。

    用户关注领域：装备健康/模拟器/雷达/卫通/智能体/仿真/软件/卫星/靶场/对抗。
    用于评分加权，命中关注领域的线索加分。无匹配返回空字符串。
    """
    if not text:
        return ''
    for domain, kws in MILITARY_DOMAIN_KEYWORDS.items():
        if any(k.lower() in text.lower() for k in kws):
            return domain
    return ''


# ==================== HTML 抓取基础设施（五大能力域共用）====================

def _fetch_html(url, dynamic=False, timeout=10):
    """统一 HTML 抓取：static requests 优先，dynamic=True 时尝试 playwright 动态渲染。

    返回 (html_text_or_None, error_or_None)。playwright 缺失时降级为 requests 静态抓取，
    二者均失败返回 (None, error)。绝不造假数据。
    """
    if not url:
        return None, '无 URL'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                            '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    # 1) 静态抓取（始终先尝试，速度快）
    try:
        resp = http_requests.get(url, timeout=timeout, headers=headers, allow_redirects=True)
        if resp.status_code == 200 and resp.text:
            text = resp.text
            # 简单启发式：若页面内容过短或含明显动态占位，且要求动态渲染，则升级到 playwright
            if not dynamic or len(text) > 2000:
                return text, None
    except Exception as e:
        if not dynamic:
            return None, f'静态抓取失败: {e}'
    # 2) 动态渲染（仅 dynamic=True 时尝试，playwright 缺失则降级返回静态结果或空）
    if dynamic:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            # playwright 未安装，降级：返回已抓到的静态内容或空
            try:
                return resp.text, None
            except Exception:
                return None, 'playwright 未安装且静态抓取失败'
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(user_agent=headers['User-Agent'])
                page.goto(url, timeout=timeout * 1000, wait_until='domcontentloaded')
                page.wait_for_timeout(2000)  # 等待动态内容加载
                html = page.content()
                browser.close()
                return html, None
        except Exception as e:
            return None, f'动态渲染失败: {e}'
    return None, '抓取失败'


def _scrape_html_by_category(source, config, keywords, category):
    """HTML 源按 category 分发到对应能力域抓取器。"""
    url = source.get('url', '')
    dynamic = bool(config.get('dynamic', False))
    html, err = _fetch_html(url, dynamic=dynamic, timeout=config.get('timeout', 15))
    if not html:
        return []  # 抓取失败返回空列表，不造假数据
    if category == '招投标监控':
        return _scrape_bidding(html, source, config, keywords)
    if category == '电商商机':
        return _scrape_ecommerce(html, source, config, keywords, url)
    if category == '企业客源':
        return _scrape_b2b(html, source, config, keywords, url)
    if category == '竞品情报':
        return _scrape_competitor(html, source, config, keywords, url)
    if category == '舆情痛点':
        return _scrape_forum(html, source, config, keywords, url)
    return []


# ==================== 能力域一：招投标与政企采购监控（HTML）====================

def _scrape_bidding(html, source, config, keywords):
    """解析招投标公告 HTML 页面，提取标题/链接/发布日期。

    兼容多种招投标网站列表结构，用正则启发式提取 <a> 链接与相邻日期文本。
    """
    max_items = config.get('max_items', 20)
    leads = []
    # 提取所有 <a href="...">标题</a>，过滤导航/静态资源链接
    pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{6,120})</a>', re.IGNORECASE)
    seen = set()
    for m in pattern.finditer(html):
        link = m.group(1).strip()
        title = re.sub(r'\s+', ' ', m.group(2)).strip()
        # 过滤无效链接与导航类标题
        if not link or link.startswith(('#', 'javascript:', 'mailto:')):
            continue
        if any(skip in title for skip in ['首页', '登录', '注册', '更多', '下一页', '上一页', '关于我们']):
            continue
        # 补全相对链接
        if link.startswith('/'):
            from urllib.parse import urlparse
            base = urlparse(source.get('url', '')).scheme + '://' + urlparse(source.get('url', '')).netloc
            link = base + link
        # 关键词过滤
        text = title
        if keywords and not any(k in text for k in keywords):
            continue
        if link in seen:
            continue
        seen.add(link)
        leads.append({
            'company': _extract_company(title) or title[:40],
            'opportunity_name': title,
            'contact_name': '', 'phone': '', 'email': '',
            'industry': _detect_industry(text),
            'region': source.get('region', '全国'),
            'source': '招投标监控',
            'link': link,
            'remark': title[:100],
            'raw_data': json.dumps({'title': title, 'link': link, 'category': '招投标监控'}, ensure_ascii=False),
        })
        if len(leads) >= max_items:
            break
    return leads


# ==================== 能力域二：跨境与国内电商商机（爆款挖掘）====================

# 电商高需求低竞争评分：rank 越小（榜单越靠前）需求越高，rating_count 适中竞争越低
def _ecommerce_score(rank, rating_count, price_str):
    """计算电商爆款评分：高需求（榜单靠前/评价多）+ 低竞争（评价数适中）。

    评分逻辑：
    - 基础 40 分
    - 榜单排名：前 10 名 +30，前 30 名 +20，前 50 名 +10
    - 评价数：100-1000 为低竞争蓝海 +20，1000-5000 +10，>5000 竞争激烈 -5
    - 价格：中高客单价（100-2000）+10，过低（<50）价格战激烈 -5
    """
    score = 40
    reasons = []
    try:
        rank_int = int(rank) if rank else 999
    except Exception:
        rank_int = 999
    if rank_int <= 10:
        score += 30; reasons.append('榜单Top10需求旺盛')
    elif rank_int <= 30:
        score += 20; reasons.append('榜单Top30需求较高')
    elif rank_int <= 50:
        score += 10; reasons.append('榜单Top50有一定需求')
    try:
        rc = int(rating_count) if rating_count else 0
    except Exception:
        rc = 0
    if 100 <= rc <= 1000:
        score += 20; reasons.append('评价数适中(100-1000)属低竞争蓝海')
    elif 1000 < rc <= 5000:
        score += 10; reasons.append('评价数中等(1000-5000)')
    elif rc > 5000:
        score -= 5; reasons.append('评价数>5000竞争激烈')
    # 价格解析
    price_val = 0
    if price_str:
        pm = re.search(r'[\d,]+\.?\d*', price_str.replace(',', ''))
        if pm:
            price_val = float(pm.group())
    if 100 <= price_val <= 2000:
        score += 10; reasons.append('中高客单价利润空间大')
    elif price_val < 50 and price_val > 0:
        score -= 5; reasons.append('低客单价易陷价格战')
    score = max(0, min(100, score))
    return score, '；'.join(reasons) if reasons else '信息有限'


def _scrape_ecommerce(html, source, config, keywords, base_url):
    """解析电商榜单/商品列表 HTML，提取商品名/价格/排名/评价数，计算爆款评分。

    兼容 Amazon Best Sellers 等榜单页结构，正则提取商品卡片。
    """
    max_items = config.get('max_items', 20)
    leads = []
    # Amazon Best Sellers 商品卡片常见结构：含商品标题的 <a> + 价格 + 排名
    # 启发式：提取 zg-item / p13n-asin 等容器内的标题与价格
    items = re.findall(
        r'<div[^>]*zg[-_]item[^>]*>(.*?)</div>\s*</div>',
        html, re.IGNORECASE | re.DOTALL
    )
    if not items:
        # 兜底：提取所有带商品链接的 <a>
        items = re.findall(r'(<a[^>]*dp/[A-Z0-9]+[^>]*>.*?</a>)', html, re.IGNORECASE | re.DOTALL)
    seen = set()
    for idx, block in enumerate(items[:max_items * 2], 1):
        # 商品标题
        title_m = re.search(r'<a[^>]*>([^<]{8,200})</a>', block, re.IGNORECASE)
        if not title_m:
            continue
        title = re.sub(r'\s+', ' ', title_m.group(1)).strip()
        if not title or len(title) < 8:
            continue
        # 商品链接
        link_m = re.search(r'href=["\']([^"\']*(?:dp|product|item)[^"\']*)["\']', block, re.IGNORECASE)
        link = link_m.group(1) if link_m else ''
        if link.startswith('/'):
            from urllib.parse import urlparse
            base = urlparse(base_url).scheme + '://' + urlparse(base_url).netloc
            link = base + link
        # 价格
        price_m = re.search(r'[\$￥¥]\s*[\d,]+\.?\d*', block)
        price_str = price_m.group(0).strip() if price_m else ''
        # 评价数
        rating_m = re.search(r'([\d,]+)\s*(?:ratings|评价|评论)', block, re.IGNORECASE)
        rating_count = rating_m.group(1).replace(',', '') if rating_m else '0'
        # 关键词过滤
        if keywords and not any(k in title for k in keywords):
            continue
        if link in seen:
            continue
        seen.add(link or title)
        rank = idx
        score, reason = _ecommerce_score(rank, rating_count, price_str)
        leads.append({
            'company': source.get('name', '电商平台'),
            'opportunity_name': f'【榜单#{rank}】{title[:60]}',
            'contact_name': '', 'phone': '', 'email': '',
            'industry': _detect_industry(title),
            'region': source.get('region', '海外'),
            'source': '电商商机',
            'link': link,
            'remark': f'{title[:80]}；价格:{price_str}；评价:{rating_count}；爆款评分:{score}（{reason}）',
            'raw_data': json.dumps({
                'title': title, 'link': link, 'price': price_str,
                'rating_count': rating_count, 'rank': rank,
                'ecommerce_score': score, 'reason': reason,
                'category': '电商商机'
            }, ensure_ascii=False),
        })
        if len(leads) >= max_items:
            break
    return leads


# ==================== 能力域三：精准 B2B 外贸/内贸客源提取 ====================

def _scrape_b2b(html, source, config, keywords, base_url):
    """解析企业信用公示/黄页 HTML，批量提取新注册企业信息。

    启发式提取企业名称、法定代表人、注册资本、成立日期、联系方式。
    """
    max_items = config.get('max_items', 20)
    leads = []
    # 企业名称常见模式：含"有限公司"/"有限责任公司"/"集团"的文本
    company_pattern = re.compile(
        r'([\u4e00-\u9fa5A-Za-z]{2,30}(?:有限公司|有限责任公司|股份有限公司|集团有限公司|研究院|中心))'
    )
    seen = set()
    # 提取企业名后，向上下文窗口寻找关联信息（法人/日期/电话）
    for m in company_pattern.finditer(html):
        company = m.group(1).strip()
        if company in seen:
            continue
        seen.add(company)
        # 在企业名附近 ±300 字符内查找关联字段
        start = max(0, m.start() - 300)
        ctx = html[start:m.end() + 300]
        # 法定代表人
        legal_m = re.search(r'(?:法定代表人|负责人)[：:\s]*([\u4e00-\u9fa5]{2,4})', ctx)
        contact_name = legal_m.group(1) if legal_m else ''
        # 成立日期
        date_m = re.search(r'(?:成立日期|注册日期|成立)[：:\s]*(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', ctx)
        reg_date = date_m.group(1) if date_m else ''
        # 电话
        phone_m = re.search(r'(?:联系电话|电话|联系方式)[：:\s]*(\d[\d\-*]{6,15})', ctx)
        phone = phone_m.group(1) if phone_m else ''
        # 关键词过滤（按企业名/上下文）
        if keywords and not any(k in company for k in keywords) and not any(k in ctx for k in keywords):
            continue
        leads.append({
            'company': company,
            'opportunity_name': f'新注册企业：{company}',
            'contact_name': contact_name,
            'phone': phone, 'email': '',
            'industry': _detect_industry(company + ctx[:100]),
            'region': source.get('region', '全国'),
            'source': '企业客源',
            'link': source.get('url', ''),
            'remark': f'{company}；法人:{contact_name or "—"}；成立:{reg_date or "—"}',
            'raw_data': json.dumps({
                'company': company, 'legal_rep': contact_name,
                'reg_date': reg_date, 'phone': phone, 'category': '企业客源'
            }, ensure_ascii=False),
        })
        if len(leads) >= max_items:
            break
    return leads


# ==================== 能力域四：竞争对手情报监听 ====================

# 竞品变动检测：价格变动 / 新品上线 / 促销活动
_COMPETITOR_PRICE_RE = re.compile(r'(?:价格|价|￥|¥|\$)\s*[\d,]+\.?\d*', re.IGNORECASE)
_COMPETITOR_PROMO_RE = re.compile(r'(?:促销|折扣|优惠|限时|特价|直降|满减|新品|上市|发布)', re.IGNORECASE)


def _scrape_competitor(html, source, config, keywords, base_url):
    """监控竞品官网，提取产品名/价格/促销动态，与上次抓取对比检测变动。

    变动检测：将本次抓取的产品价格与 raw_data 中上次记录对比，价格变动/新品/促销标记为线索。
    """
    max_items = config.get('max_items', 20)
    leads = []
    competitor_name = source.get('name', '竞品官网')
    # 提取产品卡片：含产品名的 <a> + 价格
    product_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{4,100})</a>.*?'
        r'(?:价格|价|￥|¥|\$)\s*([\d,]+\.?\d*)?',
        re.IGNORECASE | re.DOTALL
    )
    seen = set()
    for m in product_pattern.finditer(html):
        link = m.group(1).strip()
        name = re.sub(r'\s+', ' ', m.group(2)).strip()
        price = m.group(3) or ''
        if not name or any(skip in name for skip in ['首页', '登录', '关于', '联系']):
            continue
        if link.startswith('/'):
            from urllib.parse import urlparse
            base = urlparse(base_url).scheme + '://' + urlparse(base_url).netloc
            link = base + link
        if link in seen:
            continue
        seen.add(link)
        # 关键词过滤
        if keywords and not any(k in name for k in keywords):
            continue
        # 促销检测
        ctx_start = max(0, m.start() - 200)
        ctx = html[ctx_start:m.end() + 200]
        promo_match = _COMPETITOR_PROMO_RE.search(ctx)
        promo = promo_match.group(0) if promo_match else ''
        leads.append({
            'company': competitor_name,
            'opportunity_name': f'竞品动态：{name[:50]}',
            'contact_name': '', 'phone': '', 'email': '',
            'industry': _detect_industry(name),
            'region': source.get('region', '全国'),
            'source': '竞品情报',
            'link': link,
            'remark': f'{competitor_name} - {name[:40]}；价格:{("￥"+price) if price else "—"}；'
                      f'{"促销:"+promo if promo else "常规"}',
            'raw_data': json.dumps({
                'competitor': competitor_name, 'product': name,
                'price': price, 'promo': promo, 'link': link,
                'category': '竞品情报', 'scraped_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, ensure_ascii=False),
        })
        if len(leads) >= max_items:
            break
    # 变动检测说明：实际价格对比需读取上次 raw_data，因抓取器无 DB 访问，对比逻辑在评估阶段执行
    return leads


# ==================== 能力域五：行业痛点与舆情分析 ====================

# 痛点/负面情绪关键词：这些未被满足的怨言往往是创业或新功能商机
_PAIN_POINT_KW = [
    '难用', '不能', '无法', '报错', '崩溃', '太贵', '不支持', '缺少', '缺失',
    '希望', '建议', '什么时候', '为什么', '卡顿', '闪退', '不好', '差', '吐槽',
    '需求', '期待', '如果', '要是有', '能不能', '可以吗', 'bug', '问题', '缺陷'
]
# 强意向商机关键词
_OPPORTUNITY_KW = ['采购', '招标', '需求', '项目', '方案', '开发', '建设', '合作']


def _scrape_forum(html, source, config, keywords, base_url):
    """抓取垂直论坛/社区帖子，提取用户吐槽与需求痛点，挖掘未满足商机。

    痛点分析：识别含负面/期待关键词的帖子标题，按热度（回复数/点赞数）排序，
    将高频痛点转化为商机线索。
    """
    max_items = config.get('max_items', 20)
    leads = []
    # 提取帖子标题链接（知乎热榜/贴吧帖子通用结构）
    post_pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{6,150})</a>',
        re.IGNORECASE
    )
    seen = set()
    for m in post_pattern.finditer(html):
        link = m.group(1).strip()
        title = re.sub(r'\s+', ' ', m.group(2)).strip()
        if not link or link.startswith(('#', 'javascript:', 'mailto:')):
            continue
        if any(skip in title for skip in ['首页', '登录', '注册', '下载APP', '更多']):
            continue
        if link.startswith('/'):
            from urllib.parse import urlparse
            base = urlparse(base_url).scheme + '://' + urlparse(base_url).netloc
            link = base + link
        if link in seen:
            continue
        seen.add(link)
        # 痛点检测：标题含负面/期待关键词才纳入（挖掘未满足需求）
        is_pain_point = any(k in title for k in _PAIN_POINT_KW)
        has_opportunity = any(k in title for k in _OPPORTUNITY_KW)
        # 关键词过滤：命中关注领域 或 含痛点/商机关键词
        if keywords:
            if not any(k in title for k in keywords) and not is_pain_point and not has_opportunity:
                continue
        elif not is_pain_point and not has_opportunity:
            continue
        # 痛点评分：痛点词越多分越高，含商机关键词额外加分
        pain_count = sum(1 for k in _PAIN_POINT_KW if k in title)
        opp_count = sum(1 for k in _OPPORTUNITY_KW if k in title)
        score = 40 + pain_count * 12 + opp_count * 15
        score = min(100, score)
        pain_type = '需求痛点' if is_pain_point else ('潜在商机' if has_opportunity else '行业动态')
        leads.append({
            'company': source.get('name', '社区讨论'),
            'opportunity_name': f'【{pain_type}】{title[:60]}',
            'contact_name': '', 'phone': '', 'email': '',
            'industry': _detect_industry(title),
            'region': source.get('region', '全国'),
            'source': '舆情痛点',
            'link': link,
            'remark': f'{title[:80]}；痛点评分:{score}（命中{pain_count}个痛点词+{opp_count}个商机词）',
            'raw_data': json.dumps({
                'title': title, 'link': link, 'pain_type': pain_type,
                'pain_count': pain_count, 'opp_count': opp_count,
                'sentiment_score': score, 'category': '舆情痛点'
            }, ensure_ascii=False),
        })
        if len(leads) >= max_items:
            break
    return leads


def _scrape_rss(url, keywords, max_items=20):
    """抓取 RSS 源，解析 item 为线索。网络不可用时返回空列表。

    link 取 RSS item 的真实 <link>（公告原文链接），industry 由 _detect_industry 自动分类。
    """
    if not url:
        return []
    try:
        resp = http_requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0 CRM-Lead-Bot'})
        if resp.status_code != 200 or not resp.content:
            return []
        root = ET.fromstring(resp.content)
        items = []
        for item in root.iter('item'):
            title = (item.findtext('title') or '').strip()
            desc = (item.findtext('description') or '').strip()
            link = (item.findtext('link') or '').strip()
            pub = (item.findtext('pubDate') or '').strip()
            text = f'{title} {desc}'
            # 关键词命中过滤（无关键词则全部保留）
            if keywords and not any(k in text for k in keywords):
                continue
            items.append({
                'company': _extract_company(title) or title[:40],
                'opportunity_name': title,
                'contact_name': '',
                'phone': '',
                'email': '',
                'industry': _detect_industry(text),
                'region': '全国',
                'source': 'RSS抓取',
                'link': link,
                'remark': f'{title[:80]}；发布:{pub[:16]}' if pub else title[:100],
                'raw_data': json.dumps({'title': title, 'link': link, 'desc': desc[:200]}, ensure_ascii=False),
            })
            if len(items) >= max_items:
                break
        return items
    except Exception:
        return []


def _scrape_api(url, config, keywords, industry, region):
    """调用第三方 API 接口抓取线索。无 URL 时不生成数据（返回空列表）。"""
    if not url:
        return []
    try:
        headers = config.get('headers', {'User-Agent': 'Mozilla/5.0'})
        params = config.get('params', {})
        resp = http_requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return []
        data = resp.json()
        # 兼容 {data:[...]} 或 [...] 两种结构
        records = data.get('data', data) if isinstance(data, dict) else data
        if not isinstance(records, list):
            return []
        leads = []
        for r in records[:config.get('count', 10)]:
            leads.append({
                'company': r.get('company') or r.get('name') or '',
                'opportunity_name': r.get('opportunity_name') or r.get('title') or r.get('project_name') or '',
                'contact_name': r.get('contact_name') or r.get('contact') or '',
                'phone': r.get('phone') or '',
                'email': r.get('email') or '',
                'industry': r.get('industry') or industry,
                'region': r.get('region') or region,
                'source': 'API接口',
                'link': r.get('link') or r.get('url') or '',
                'remark': r.get('remark') or r.get('desc') or '',
                'raw_data': json.dumps(r, ensure_ascii=False),
            })
        return leads
    except Exception:
        return []  # API 调用失败，不生成演示数据


# 按行业分组的示例公司池与商机名称模板（用于离线演示与测试，覆盖本公司关注领域）
_SAMPLE_POOL = {
    '卫星遥感': {
        'companies': [
            ('航天宏图信息技术', '卫星遥感'), ('中科卫星空间技术', '卫星遥感'),
            ('欧比特宇航科技', '卫星遥感'), ('二十一世纪空间技术应用', '卫星遥感'),
            ('航天世景信息技术', '卫星遥感'), ('长光卫星技术', '卫星遥感'),
            ('银河航天科技', '卫星遥感'),
        ],
        'opps': [
            '{company}卫星遥感数据采购项目',
            '高分辨率遥感影像数据采购需求',
            '自然资源遥感监测系统建设',
            '农业遥感估产项目采购',
        ],
    },
    '卫星通信': {
        'companies': [
            ('中交通信信息科技', '卫星通信'), ('鑫诺卫星通信', '卫星通信'),
            ('亚太卫星宽带通信', '卫星通信'), ('海卫通信技术', '卫星通信'),
            ('北斗星通导航技术', '卫星通信'), ('中兴通讯', '卫星通信'),
        ],
        'opps': [
            '{company}卫星通信终端批量采购',
            'VSAT卫星通信站建设项目',
            '机载卫星通信终端设备采购',
            '应急卫星通信系统建设需求',
        ],
    },
    'AI智能体': {
        'companies': [
            ('智谱华章科技', 'AI智能体'), ('百川智能', 'AI智能体'),
            ('月之暗面科技', 'AI智能体'), ('科大讯飞', 'AI智能体'),
            ('云知声智能科技', 'AI智能体'), ('旷视科技', 'AI智能体'),
            ('中科星图', 'AI智能体'),
        ],
        'opps': [
            '{company}AI智能体开发服务采购',
            '企业级AI智能体平台建设需求',
            '智能客服智能体定制开发项目',
            '行业大模型智能体应用需求',
        ],
    },
    '军工装备': {
        'companies': [
            ('航天科工集团', '军工装备'), ('中国电子科技集团', '军工装备'),
            ('中国兵器工业集团', '军工装备'), ('中国航空工业集团', '军工装备'),
            ('航天科技集团', '军工装备'),
        ],
        'opps': [
            '武器装备配套采购项目',
            '军用信息系统集成需求',
            '装备研制协作配套采购',
            '军用通信设备采购需求',
        ],
    },
    '信息技术': {
        'companies': [
            ('航天信息科技', '信息技术'), ('华为技术', '信息技术'),
            ('紫光展锐', '信息技术'), ('海康威视', '信息技术'),
            ('曙光信息产业', '信息技术'), ('大疆创新', '信息技术'),
        ],
        'opps': [
            '{company}信息化系统建设需求',
            '数字化转型平台采购项目',
            '智慧城市建设需求',
            '信息安全系统采购',
        ],
    },
}
_SAMPLE_REMARKS = [
    '急需采购一批设备，预算充足，希望尽快对接',
    '近期有招标计划，关注技术方案与报价',
    '项目已立项，正在寻找合格供应商',
    '老客户介绍，有明确需求，计划本月签约',
    '主动咨询产品功能，希望安排演示',
    '展会获客，对方案感兴趣，需进一步沟通',
]
_SAMPLE_CONTACTS = ['张总', '李经理', '王主任', '赵工', '陈总', '刘经理']
_SAMPLE_REGIONS = ['北京', '上海', '深圳', '西安', '成都', '南京', '全国']


def _scrape_sample(count, keywords, industry, region):
    """生成示例线索（仅供手动测试，不预置为自动抓取源）。

    根据 industry 配置选取对应行业池生成公司+商机名称。
    注意：示例数据不包含真实链接（link 为空），避免误导。
    industry 为逗号分隔的多行业（如 "卫星遥感,卫星通信"），命中任一池即纳入抽取范围。
    """
    industry_str = industry or ''
    matched = [(k, v) for k, v in _SAMPLE_POOL.items() if k in industry_str]
    pools = matched if matched else list(_SAMPLE_POOL.items())
    count = min(int(count or 5), 20)
    leads = []
    for _ in range(count):
        pool_key, pool = random.choice(pools)
        company, ind = random.choice(pool['companies'])
        opp_name = random.choice(pool['opps']).format(company=company)
        leads.append({
            'company': company,
            'opportunity_name': opp_name,
            'contact_name': random.choice(_SAMPLE_CONTACTS),
            'phone': f'138{random.randint(10000000, 99999999)}',
            'email': '',
            'industry': ind,
            'region': region or random.choice(_SAMPLE_REGIONS),
            'source': random.choice(['展会', '官网咨询', '外部抓取', '老客户介绍', '官网监控']),
            'link': '',  # 示例数据无真实链接
            'remark': random.choice(_SAMPLE_REMARKS),
            'raw_data': json.dumps({'sample': True, 'opportunity_name': opp_name}, ensure_ascii=False),
        })
    return leads


def _extract_company(text):
    """从标题文本中启发式提取公司名。"""
    m = re.search(r'([\u4e00-\u9fa5]{2,10}(?:公司|科技|集团|有限|研究院|中心|股份))', text or '')
    return m.group(1) if m else None


def _persist_leads(cursor, leads_data, source_id, source_name, source_category=None):
    """线索入库（多维跨源去重），返回新增数。

    去重策略（跨源去重，避免同一公告从不同查询/源重复入库）：
    1. link 非空时，按 link 全局去重（同一公告链接只入库一次）
    2. opportunity_name+company 去重（同一项目同一采购方只入库一次）
    3. 兜底：source_id+company+phone 去重

    source_category 由调用方传入（来自 lead_sources.category），用于给线索打能力域标签。
    """
    if source_category is None and source_id:
        try:
            cursor.execute("SELECT category FROM lead_sources WHERE id=?", (source_id,))
            row = cursor.fetchone()
            if row:
                source_category = row['category'] or ''
        except Exception:
            source_category = ''
    inserted = 0
    for lead in leads_data:
        company = (lead.get('company') or '').strip()
        if not company:
            continue
        link = (lead.get('link') or '').strip()
        opp_name = (lead.get('opportunity_name') or '').strip()
        category = lead.get('category') or source_category or ''
        # 军采监控：链接黑名单二次验证（LLM 降级路径可能漏过）
        if category == '军采监控' and link and _is_junk_url(link):
            continue
        # 多维跨源去重检查
        dup = False
        if link:
            cursor.execute("SELECT id FROM scraped_leads WHERE link=?", (link,))
            if cursor.fetchone():
                dup = True
        if not dup and opp_name and company:
            cursor.execute(
                "SELECT id FROM scraped_leads WHERE opportunity_name=? AND company=?",
                (opp_name, company)
            )
            if cursor.fetchone():
                dup = True
        if not dup:
            cursor.execute(
                "SELECT id FROM scraped_leads WHERE source_id=? AND company=? AND phone=?",
                (source_id, company, lead.get('phone', ''))
            )
            if cursor.fetchone():
                dup = True
        if dup:
            continue
        cursor.execute("""
            INSERT INTO scraped_leads (source_id, company, opportunity_name, contact_name, phone, email,
                                        industry, region, source, link, remark, raw_data, category,
                                        publish_date, deadline, budget, procurement_method,
                                        tender_no, agency, agency_phone,
                                        status, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
        """, (
            source_id, company, opp_name,
            lead.get('contact_name', ''), lead.get('phone', ''),
            lead.get('email', ''), lead.get('industry', ''), lead.get('region', ''),
            lead.get('source', source_name), link,
            lead.get('remark', ''), lead.get('raw_data', ''), category,
            lead.get('publish_date', ''), lead.get('deadline', ''),
            lead.get('budget', ''), lead.get('procurement_method', ''),
            lead.get('tender_no', ''), lead.get('agency', ''), lead.get('agency_phone', ''),
        ))
        inserted += 1
    return inserted


def _mark_scraped(cursor, source_id):
    cursor.execute("UPDATE lead_sources SET last_scraped_at=? WHERE id=?",
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), source_id))


def _cleanup_expired_leads(cursor, days=30):
    """清理过期线索：删除超过指定天数的 pending/evaluated 线索。

    已分配(imported)的线索保留审计。
    军采类商机有截止日期，过截止日期的优先清理。
    注：rejected 状态已不再使用（拒绝即删除），此处仅清理 pending/evaluated。
    """
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("""
        DELETE FROM scraped_leads
        WHERE status IN ('pending', 'evaluated')
        AND scraped_at < ?
    """, (cutoff,))
    deleted = cursor.rowcount
    # 额外清理：已过投标截止日期的军采线索（即使未到30天）
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        cursor.execute("""
            DELETE FROM scraped_leads
            WHERE category='军采监控' AND deadline IS NOT NULL AND deadline != ''
            AND deadline < ? AND status IN ('pending', 'evaluated')
        """, (today,))
        deleted += cursor.rowcount
    except Exception:
        pass
    return deleted


# ==================== 线索队列管理 ====================

@leads_bp.route('/api/leads/cleanup-expired', methods=['POST'])
@token_required
def cleanup_expired_leads():
    """清理过期线索（超过指定天数的 pending/evaluated）。

    默认清理30天前的线索；军采类过投标截止日期的也清理。已分配线索保留。
    """
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cursor = db.cursor()
    data = request.get_json(silent=True) or {}
    days = int(data.get('days', 30))
    deleted = _cleanup_expired_leads(cursor, days)
    db.commit()
    record_operation_log(payload['username'], '清理过期线索', '智能线索管理',
                         f'清理 {deleted} 条过期线索（>{days}天或已过截止日期）')
    return jsonify({'code': 200, 'message': f'已清理 {deleted} 条过期线索',
                    'data': {'deleted': deleted}})


@leads_bp.route('/api/leads', methods=['GET'])
@token_required
def list_leads():
    """线索队列列表，支持 status/source_id/keyword/category 筛选。

    默认排除 rejected 状态（拒绝即删除，不应再有 rejected 线索；
    此条件作为双重保险，防止历史遗留数据混入列表）。
    """
    status = request.args.get('status', '')
    source_id = request.args.get('source_id', '')
    source = request.args.get('source', '')
    keyword = request.args.get('keyword', '')
    category = request.args.get('category', '')

    db = get_db()
    cursor = db.cursor()
    conditions, params = [], []
    if status:
        conditions.append("sl.status = ?")
        params.append(status)
    else:
        # 未指定状态时默认排除 rejected（历史遗留数据不显示）
        conditions.append("sl.status != 'rejected'")
    if source_id:
        conditions.append("sl.source_id = ?")
        params.append(source_id)
    if source:
        # 按来源文本筛选（如 AI商机识别转入的线索，source_id 为空只有 source 文本）
        conditions.append("sl.source = ?")
        params.append(source)
    if category:
        conditions.append("sl.category = ?")
        params.append(category)
    if keyword:
        conditions.append("(sl.company LIKE ? OR sl.remark LIKE ? OR sl.contact_name LIKE ? OR sl.opportunity_name LIKE ? OR sl.tender_no LIKE ? OR sl.agency LIKE ?)")
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw, kw, kw, kw])
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    cursor.execute(f"""
        SELECT sl.*, s.name as source_name, u.name as assigned_name
        FROM scraped_leads sl
        LEFT JOIN lead_sources s ON sl.source_id = s.id
        LEFT JOIN users u ON sl.assigned_to = u.username
        {where}
        ORDER BY sl.scraped_at DESC
    """, params)
    rows = [dict(r) for r in cursor.fetchall()]

    # 统计各状态数量
    cursor.execute("""
        SELECT status, COUNT(*) as cnt FROM scraped_leads GROUP BY status
    """)
    stats = {r['status']: r['cnt'] for r in cursor.fetchall()}

    # 统计各能力域类别数量
    cursor.execute("""
        SELECT COALESCE(category, '') as category, COUNT(*) as cnt
        FROM scraped_leads GROUP BY category
    """)
    category_stats = {r['category']: r['cnt'] for r in cursor.fetchall()}

    return jsonify({'code': 200, 'message': 'success',
                    'data': {'list': rows, 'stats': stats, 'category_stats': category_stats}})


@leads_bp.route('/api/leads/evaluate-batch', methods=['POST'])
@token_required
def evaluate_batch_leads():
    """批量评估所有 pending 线索的意向分值并推荐分配。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '仅主任/院长可评估线索', 'data': None})
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM scraped_leads WHERE status='pending'")
    pending = [dict(r) for r in cursor.fetchall()]
    if not pending:
        return jsonify({'code': 200, 'message': '没有待评估的线索', 'data': {'evaluated': 0}})

    industry_stats, salespeople = _load_eval_context(cursor)
    evaluated = 0
    for lead in pending:
        score, reason = _evaluate_lead(lead, industry_stats)
        assignee = _assign_lead(lead, salespeople)
        # assign_reason 持久化推荐依据：综合评分+维度分数+Top5候选，便于前端展示科学决策依据
        assign_reason_json = json.dumps({
            'score': assignee.get('score') if assignee else None,
            'reason': assignee.get('reason') if assignee else None,
            'details': assignee.get('details') if assignee else None,
            'all_candidates': assignee.get('all_candidates') if assignee else None,
        }, ensure_ascii=False) if assignee else None
        cursor.execute("""
            UPDATE scraped_leads SET intent_score=?, eval_reason=?, assigned_to=?,
                                     assign_reason=?, status='evaluated', evaluated_at=?
            WHERE id=?
        """, (score, reason, assignee['username'] if assignee else None,
              assign_reason_json,
              datetime.now().strftime('%Y-%m-%d %H:%M:%S'), lead['id']))
        evaluated += 1
    db.commit()
    record_operation_log(payload['username'], '批量评估线索', '智能线索管理',
                         f'批量评估 {evaluated} 条线索')
    return jsonify({'code': 200, 'message': f'已评估 {evaluated} 条线索',
                    'data': {'evaluated': evaluated}})


@leads_bp.route('/api/leads/<int:lead_id>/evaluate', methods=['POST'])
@token_required
def evaluate_single_lead(lead_id):
    """评估单条线索。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM scraped_leads WHERE id=?", (lead_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '线索不存在', 'data': None})
    lead = dict(row)
    industry_stats, salespeople = _load_eval_context(cursor)
    score, reason = _evaluate_lead(lead, industry_stats)
    assignee = _assign_lead(lead, salespeople)
    assign_reason_json = json.dumps({
        'score': assignee.get('score') if assignee else None,
        'reason': assignee.get('reason') if assignee else None,
        'details': assignee.get('details') if assignee else None,
        'all_candidates': assignee.get('all_candidates') if assignee else None,
    }, ensure_ascii=False) if assignee else None
    cursor.execute("""
        UPDATE scraped_leads SET intent_score=?, eval_reason=?, assigned_to=?,
                                 assign_reason=?, status='evaluated', evaluated_at=?
        WHERE id=?
    """, (score, reason, assignee['username'] if assignee else None,
          assign_reason_json,
          datetime.now().strftime('%Y-%m-%d %H:%M:%S'), lead_id))
    db.commit()
    return jsonify({'code': 200, 'message': '评估完成',
                    'data': {'intent_score': score, 'reason': reason,
                             'assigned_to': assignee}})


@leads_bp.route('/api/leads/<int:lead_id>/assign', methods=['POST'])
@token_required
def assign_lead(lead_id):
    """分配线索：创建客户 + 自动生成商机，归属指定销售，线索标记为 imported。

    请求体：assigned_to（可选，默认用 AI 推荐分配）

    业务流程：线索 → [分配] → 创建客户 + 创建商机（引导需求阶段）→ 形成"线索→商机→合同"完整链路。
    """
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    data = request.get_json(silent=True) or {}
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM scraped_leads WHERE id=?", (lead_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '线索不存在', 'data': None})
    lead = dict(row)

    assigned_to = data.get('assigned_to') or lead.get('assigned_to')
    if not assigned_to:
        # 未指定则用 AI 推荐
        _, salespeople = _load_eval_context(cursor)
        assignee = _assign_lead(lead, salespeople)
        assigned_to = assignee['username'] if assignee else None
    if not assigned_to:
        return jsonify({'code': 400, 'message': '无可分配的销售人员', 'data': None})

    try:
        new_cust_id, new_biz_id = _do_assign_lead(cursor, lead, assigned_to)
        db.commit()
        cursor.execute("SELECT name FROM users WHERE username=?", (assigned_to,))
        sp = cursor.fetchone()
        sp_name = sp['name'] if sp else assigned_to
        record_operation_log(payload['username'], '分配线索', '智能线索管理',
                             f'线索「{lead.get("company")}」分配给 {sp_name}，'
                             f'已创建客户 ID:{new_cust_id} + 商机 ID:{new_biz_id}')
        return jsonify({'code': 200, 'message': f'已分配给 {sp_name}，已创建客户和商机',
                        'data': {'customer_id': new_cust_id,
                                 'business_id': new_biz_id,
                                 'assigned_to': assigned_to}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


def _do_assign_lead(cursor, lead, assigned_to):
    """单条线索执行分配核心（与 HTTP 解耦，便于批量复用；不 commit，由外层控制事务）。
    返回 (new_cust_id, new_biz_id)。抛异常由外层统一处理（rollback/记录失败）。
    """
    lead_id = lead['id']
    # 1) 创建客户，归属该销售
    cursor.execute("""
        INSERT INTO customers (name, company, phone, level, source, owner_id,
                               contact_name, industry, region, created_at, last_follow)
        VALUES (?, ?, ?, 'C', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """, (
        lead.get('contact_name') or lead.get('company'),
        lead.get('company'), lead.get('phone', ''),
        f'智能线索-{lead.get("source", "")}', assigned_to,
        lead.get('contact_name', ''), lead.get('industry', ''), lead.get('region', ''),
    ))
    new_cust_id = cursor.lastrowid

    # 2) 自动创建商机：线索转化为商机（引导需求阶段），形成"线索→商机→合同"完整链路
    biz_title = (lead.get('opportunity_name') or lead.get('company') or '新商机').strip()
    biz_source = f'智能线索-{lead.get("source", "")}'
    biz_amount = _parse_budget(lead.get('budget'))
    biz_note_parts = [f'由线索 ID:{lead_id} 自动转化']
    if lead.get('intent_score') is not None:
        biz_note_parts.append(f'线索意向分{lead["intent_score"]}')
    if lead.get('eval_reason'):
        biz_note_parts.append(f'评估：{lead["eval_reason"]}')
    if lead.get('link'):
        biz_note_parts.append(f'来源链接：{lead["link"]}')
    biz_note = '；'.join(biz_note_parts)
    cursor.execute("""
        INSERT INTO business (title, cust_id, stakeholder, amount, stage, probability,
                              predict_date, source, industry, region, owner_id,
                              address, customer_relation, weekly_plan, next_week_plan,
                              plan_week, note, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
    """, (
        biz_title, new_cust_id, lead.get('contact_name', ''), biz_amount,
        '引导需求阶段', 10, '', biz_source,
        lead.get('industry', ''), lead.get('region', ''), assigned_to,
        lead.get('company', ''), '', '', '', '', biz_note,
    ))
    new_biz_id = cursor.lastrowid

    # 3) 线索标记 imported，记录关联 biz_id
    cursor.execute("""
        UPDATE scraped_leads SET status='imported', assigned_to=?, business_id=?,
                                 evaluated_at=?
        WHERE id=?
    """, (assigned_to, new_biz_id,
          datetime.now().strftime('%Y-%m-%d %H:%M:%S'), lead_id))
    return new_cust_id, new_biz_id


# ==================== 批量分配：预览 + 主任调整 + 确认执行 ====================

@leads_bp.route('/api/leads/allocation-preview', methods=['POST'])
@token_required
def allocation_preview():
    """生成批量分配草案（只读）。主任可在此基础上调整后再提交确认。

    请求体：
      - mode: 'recommended'（AI 多维度综合推荐/历史对接经验+知识库）| 'average'（按数量均匀摊派）
      - scope: 'evaluated'（仅已评估未分配）| 'pending_eval'（先批量评估再分配）| 'all_unassigned'（以上两者）
      - lead_ids: [int,...]（可选，scope 为空时用）
      - re_evaluate: bool（可选，默认 false；true 时对已评估线索重新跑推荐）
      - sales_usernames: [str,...]（可选，默认全体在职销售；指定时仅在该子集内均摊/推荐）
    """
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '仅主任/院长可操作批量分配', 'data': None})
    data = request.get_json(silent=True) or {}
    mode = data.get('mode', 'recommended')
    scope = data.get('scope', 'evaluated')
    lead_ids = data.get('lead_ids') or []
    re_evaluate = bool(data.get('re_evaluate', False))
    sales_usernames = [str(x).strip() for x in (data.get('sales_usernames') or []) if x]

    db = get_db()
    cursor = db.cursor()
    industry_stats, salespeople = _load_eval_context(cursor)
    if sales_usernames:
        sales_set = set(sales_usernames)
        salespeople = [s for s in salespeople if s['username'] in sales_set]
    sales_list = [{'username': s['username'], 'name': s['name'],
                   'biz_count': s.get('biz_count', 0)} for s in salespeople]

    # 组装线索范围
    if lead_ids:
        ph = ','.join('?' * len(lead_ids))
        cursor.execute(f"""
            SELECT * FROM scraped_leads
            WHERE id IN ({ph}) AND status != 'imported'
            ORDER BY COALESCE(intent_score, 0) DESC, id DESC
        """, lead_ids)
    elif scope == 'evaluated':
        cursor.execute("""
            SELECT * FROM scraped_leads
            WHERE status='evaluated' AND (assigned_to IS NULL OR status != 'imported')
            ORDER BY COALESCE(intent_score, 0) DESC, id DESC
        """)
    elif scope == 'pending_eval':
        cursor.execute("""
            SELECT * FROM scraped_leads WHERE status='pending'
            ORDER BY id DESC
        """)
    else:  # all_unassigned
        cursor.execute("""
            SELECT * FROM scraped_leads WHERE status IN ('pending','evaluated')
            ORDER BY COALESCE(intent_score, 0) DESC, id DESC
        """)
    leads = [dict(r) for r in cursor.fetchall()]
    if not leads:
        return jsonify({'code': 200, 'message': '暂无可分配线索',
                        'data': {'salespeople': sales_list, 'allocations': [],
                                 'distribution': {}}})

    # —— 第一步：对 pending 的先评估（只在内存算，不落库，避免主任取消后脏数据）
    valid_usernames = {s['username'] for s in salespeople}

    def _ensure_eval(lead):
        stored = lead.get('assigned_to') if lead.get('status') == 'evaluated' else None
        # 关键：若已存 assigned_to 不在当前候选集（主任缩小了范围/此人已离职/曾是主任现已排除）→ 强制重新推荐
        stored_invalid = (stored is not None) and (stored not in valid_usernames)
        if lead.get('status') != 'evaluated' or re_evaluate or not stored or stored_invalid:
            score, reason = _evaluate_lead(lead, industry_stats)
            # 推荐也必须在筛选后的销售里进行（salespeople 已按 sales_usernames 过滤）
            assignee = _assign_lead(lead, salespeople) if salespeople else None
            return score, reason, assignee
        # 已评估过的：直接用 DB 存的 assigned_to + assign_reason
        score = lead.get('intent_score') or 0
        reason = lead.get('eval_reason') or ''
        try:
            ar = json.loads(lead.get('assign_reason')) if lead.get('assign_reason') else None
        except Exception:
            ar = None
        assignee = {
            'username': stored,
            'name': next((s['name'] for s in salespeople if s['username'] == stored), stored),
            'score': ar.get('score') if ar else None,
            'reason': ar.get('reason') if ar else '',
            'details': ar.get('details') if ar else None,
        }
        return score, reason, assignee

    # 先为每条线索算出 AI 推荐结果
    evaluated = []  # (lead, score, reason, assignee_dict_or_None)
    for lead in leads:
        s, r, a = _ensure_eval(lead)
        evaluated.append((lead, s, r, a))

    # 兜底修正：任何 assignee 的 username 不在 valid_usernames 中 → 立即重新推荐
    for i, (lead, sc, rs, ass) in enumerate(evaluated):
        if ass and (ass.get('username') or '') not in valid_usernames:
            new_ass = _assign_lead(lead, salespeople) if salespeople else None
            evaluated[i] = (lead, sc, rs, new_ass)

    # —— 第二步：根据 mode 决定 proposed assigned_to
    allocations = []
    distribution = {s['username']: 0 for s in sales_list}

    if mode == 'average' and sales_list:
        # 轮询均摊：按「当前已承担本批数量 + 现有活跃商机+已分配线索数」作为优先级，最空的优先顶下一条
        # （用户要求"按数量平均分配"，但也参考现状避免把满载的人再加码）
        username_to_idx = {s['username']: i for i, s in enumerate(sales_list)}
        # 已分配（imported）线索数作为历史负载参考
        cursor.execute("""
            SELECT assigned_to, COUNT(*) as cnt FROM scraped_leads
            WHERE status='imported' AND assigned_to IS NOT NULL
            GROUP BY assigned_to
        """)
        imported_cnt = {r['assigned_to']: r['cnt'] for r in cursor.fetchall()}
        # 初始化排序槽：(当前已分配本批数、已imported数、biz_count、order、username)
        slots = []
        for s in sales_list:
            slots.append({
                'u': s['username'],
                'batch_cnt': 0,
                'imported_cnt': imported_cnt.get(s['username'], 0),
                'biz_count': s.get('biz_count', 0),
            })
        # 排序 key 小的优先接手
        def _slot_key(sl):
            return (sl['batch_cnt'], sl['imported_cnt'] + sl['biz_count'])
        for lead, score, reason, _assignee in evaluated:
            slots.sort(key=_slot_key)
            chosen = slots[0]
            proposed = chosen['u']
            chosen['batch_cnt'] += 1
            distribution[proposed] = distribution.get(proposed, 0) + 1
            allocations.append({
                'lead_id': lead['id'],
                'company': lead.get('company') or '',
                'opportunity_name': lead.get('opportunity_name') or '',
                'industry': lead.get('industry') or '',
                'intent_score': score,
                'eval_reason': reason,
                'status': lead.get('status'),
                'budget': lead.get('budget') or '',
                'category': lead.get('category') or '',
                'deadline': lead.get('deadline') or '',
                'assigned_to': proposed,
                'assigned_name': next((s['name'] for s in sales_list if s['username'] == proposed), proposed),
                'assign_mode': 'average',
                'assign_reason': f'均衡分配：第{distribution[proposed]}条',
            })
    else:  # recommended (default)
        for lead, score, reason, assignee in evaluated:
            proposed = assignee['username'] if assignee else ''
            pname = assignee['name'] if assignee else ''
            ascore = assignee.get('score') if assignee else None
            adetail = assignee.get('details') if assignee else None
            areason = assignee.get('reason') if assignee else ''
            if proposed:
                distribution[proposed] = distribution.get(proposed, 0) + 1
            allocations.append({
                'lead_id': lead['id'],
                'company': lead.get('company') or '',
                'opportunity_name': lead.get('opportunity_name') or '',
                'industry': lead.get('industry') or '',
                'intent_score': score,
                'eval_reason': reason,
                'status': lead.get('status'),
                'budget': lead.get('budget') or '',
                'category': lead.get('category') or '',
                'deadline': lead.get('deadline') or '',
                'assigned_to': proposed,
                'assigned_name': pname,
                'assign_mode': 'recommended',
                'assign_score': ascore,
                'assign_reason': areason,
                'assign_details': adetail,
            })

    return jsonify({'code': 200, 'message': '分配草案生成成功',
                    'data': {'salespeople': sales_list,
                             'allocations': allocations,
                             'distribution': distribution}})


@leads_bp.route('/api/leads/allocation-confirm', methods=['POST'])
@token_required
def allocation_confirm():
    """主任确认分配草案后批量执行。

    请求体：allocations: [{lead_id: int, assigned_to: str}]

    返回：success_count / fail_count / failures（含每条失败原因）/ imported_ids。
    每条线索独立事务：失败的不影响其他，便于主任逐条处置。
    """
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '仅主任/院长可确认分配', 'data': None})
    data = request.get_json(silent=True) or {}
    raw_list = data.get('allocations') or []
    if not raw_list:
        return jsonify({'code': 400, 'message': '分配数据为空', 'data': None})

    db = get_db()
    cursor = db.cursor()

    # 验证 assigned_to 都是有效销售
    valid_users = set()
    cursor.execute("""
        SELECT u.username FROM users u
        JOIN user_roles ur ON u.username = ur.username AND ur.role='销售'
        WHERE u.status='在职' AND u.role NOT IN ('主任', '院长')
    """)
    for r in cursor.fetchall():
        valid_users.add(r['username'])

    # 去重：同一 lead_id 只保留最后一次（前端可能重复提交同一行）
    dedup = {}
    for item in raw_list:
        lid = item.get('lead_id')
        if lid is None:
            continue
        dedup[int(lid)] = str(item.get('assigned_to') or '').strip()
    if not dedup:
        return jsonify({'code': 400, 'message': '分配数据无效', 'data': None})

    # 一次性载入所有线索（避免 N+1）
    ids = list(dedup.keys())
    ph = ','.join('?' * len(ids))
    cursor.execute(f"SELECT * FROM scraped_leads WHERE id IN ({ph})", ids)
    lead_map = {r['id']: dict(r) for r in cursor.fetchall()}

    # 缓存 user->name 用于日志
    cursor.execute("SELECT username, name FROM users")
    user_names = {r['username']: r['name'] for r in cursor.fetchall()}

    success_count = 0
    fail_count = 0
    failures = []
    imported = []

    # 逐条分配，每条独立事务（按项目约束：短事务，立即释放锁）
    for lid in ids:
        assigned_to = dedup.get(lid, '')
        if assigned_to not in valid_users:
            fail_count += 1
            failures.append({'lead_id': lid, 'message': f'负责人无效：{assigned_to or "空"}'})
            continue
        lead = lead_map.get(lid)
        if not lead:
            fail_count += 1
            failures.append({'lead_id': lid, 'message': '线索不存在'})
            continue
        if lead.get('status') == 'imported':
            fail_count += 1
            failures.append({'lead_id': lid, 'message': '线索已分配，跳过'})
            continue
        try:
            _do_assign_lead(cursor, lead, assigned_to)
            db.commit()
            success_count += 1
            imported.append({'lead_id': lid, 'assigned_to': assigned_to})
        except Exception as e:
            db.rollback()
            fail_count += 1
            failures.append({'lead_id': lid, 'message': str(e)})

    total_leads = success_count + fail_count
    record_operation_log(
        payload['username'], '批量确认分配线索', '智能线索管理',
        f'共{total_leads}条：成功{success_count}条，失败{fail_count}条'
    )
    return jsonify({'code': 200, 'message': f'执行完成：成功{success_count}条，失败{fail_count}条',
                    'data': {'success_count': success_count,
                             'fail_count': fail_count,
                             'failures': failures,
                             'imported': imported}})


def _parse_budget(budget_str):
    """解析预算金额文本为数字（元）。

    支持：'500万元'→5000000, '500万'→5000000, '3000元'→3000, '100亿'→10000000000,
          '5000000'→5000000, None/''→0
    """
    if not budget_str:
        return 0
    s = str(budget_str).strip().replace(',', '').replace('，', '')
    if not s:
        return 0
    # 提取数字部分
    m = re.search(r'(\d+(?:\.\d+)?)', s)
    if not m:
        return 0
    num = float(m.group(1))
    # 单位换算
    if '亿' in s:
        num *= 100000000
    elif '万' in s:
        num *= 10000
    return int(num) if num == int(num) else num


@leads_bp.route('/api/leads/<int:lead_id>/reject', methods=['POST'])
@token_required
def reject_lead(lead_id):
    """拒绝线索：直接从线索队列删除（不再保留为 rejected 状态）。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cursor = db.cursor()
    # 先取线索信息用于日志记录，再删除
    cursor.execute("SELECT company FROM scraped_leads WHERE id=?", (lead_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '线索不存在', 'data': None})
    company = row['company']
    cursor.execute("DELETE FROM scraped_leads WHERE id=?", (lead_id,))
    db.commit()
    record_operation_log(payload['username'], '拒绝线索', '智能线索管理',
                         f'拒绝并删除线索 ID:{lead_id}（{company}）')
    return jsonify({'code': 200, 'message': '已拒绝并删除', 'data': None})


def _ensure_manual_source(db):
    """获取/创建"人工导入"数据源（仅作为情报归属，不参与自动采集）。"""
    row = db.execute(
        "SELECT id FROM lead_sources WHERE source_type='manual' AND name='人工导入'"
    ).fetchone()
    if row:
        return row['id']
    cur = db.execute("""
        INSERT INTO lead_sources (name, source_type, url, parser_type, enabled, keywords)
        VALUES ('人工导入', 'manual', '', NULL, 0, '')
    """)
    return cur.lastrowid


@leads_bp.route('/api/leads/import', methods=['POST'])
@token_required
def import_leads():
    """手动导入线索：统一写入原始情报库（raw_intelligence），
    之后经 AI 商机识别分析 → 转入CRM → 分配销售，与自动采集共用同一链路。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    data = request.get_json(silent=True) or {}
    leads_data = data.get('leads', [])
    if not leads_data:
        return jsonify({'code': 400, 'message': '请提供线索数据', 'data': None})
    db = get_db()
    cursor = db.cursor()
    source_id = _ensure_manual_source(db)

    inserted, skipped = 0, 0
    for lead in leads_data:
        company = (lead.get('company') or '').strip()
        opp_name = (lead.get('opportunity_name') or '').strip()
        if not company and not opp_name:
            skipped += 1
            continue
        title = opp_name or company
        link = (lead.get('link') or '').strip()
        content_parts = [f'【人工导入】{title}']
        field_map = [
            ('采购单位/公司', 'company'), ('联系人', 'contact_name'), ('电话', 'phone'),
            ('邮箱', 'email'), ('行业', 'industry'), ('地区', 'region'),
            ('预算', 'budget'), ('采购方式', 'procurement_method'),
            ('发布日期', 'publish_date'), ('截止日期', 'deadline'), ('备注', 'remark'),
        ]
        for label, key in field_map:
            val = (lead.get(key) or '').strip()
            if val:
                content_parts.append(f'{label}：{val}')
        content = '；'.join(content_parts)

        # 去重：有链接按链接，否则按 公司+项目+电话
        import hashlib
        if link:
            url_hash = hashlib.sha256(link.encode()).hexdigest()
            dup = cursor.execute(
                "SELECT id FROM raw_intelligence WHERE url_hash=?", (url_hash,)
            ).fetchone()
        else:
            url_hash = hashlib.sha256(
                f'{company}|{opp_name}|{lead.get("phone", "")}'.encode()
            ).hexdigest()
            dup = cursor.execute(
                "SELECT id FROM raw_intelligence WHERE url_hash=?", (url_hash,)
            ).fetchone()
        if dup:
            skipped += 1
            continue

        cursor.execute("""
            INSERT INTO raw_intelligence (source_id, url, url_hash, title, content,
                                          snippet, publish_date, status, keywords_matched)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', '人工导入')
        """, (source_id, link, url_hash, title, content,
              content[:300], (lead.get('publish_date') or '').strip()))
        inserted += 1

    db.commit()
    record_operation_log(
        payload['username'], '导入线索', '原始情报库',
        f'人工导入 {inserted} 条至原始情报库（重复跳过 {skipped} 条）'
    )
    return jsonify({
        'code': 200,
        'message': f'已导入 {inserted} 条至原始情报库（重复跳过 {skipped} 条），请前往"AI商机识别"批量分析后转入CRM分配销售',
        'data': {'inserted': inserted, 'skipped': skipped}
    })


@leads_bp.route('/api/leads/stats', methods=['GET'])
@token_required
def leads_stats():
    """线索管理仪表盘统计。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT status, COUNT(*) as cnt FROM scraped_leads GROUP BY status
    """)
    status_stats = {r['status']: r['cnt'] for r in cursor.fetchall()}
    cursor.execute("SELECT COUNT(*) as cnt FROM lead_sources WHERE enabled=1")
    enabled_sources = cursor.fetchone()['cnt']
    cursor.execute("""
        SELECT AVG(intent_score) as avg_score FROM scraped_leads
        WHERE status IN ('evaluated','imported') AND intent_score IS NOT NULL
    """)
    avg_score = cursor.fetchone()['avg_score']
    cursor.execute("""
        SELECT assigned_to, u.name, COUNT(*) as cnt FROM scraped_leads sl
        LEFT JOIN users u ON sl.assigned_to = u.username
        WHERE sl.assigned_to IS NOT NULL GROUP BY sl.assigned_to ORDER BY cnt DESC LIMIT 5
    """)
    top_assignees = [dict(r) for r in cursor.fetchall()]
    # 各能力域类别线索数
    cursor.execute("""
        SELECT COALESCE(category, '') as category, COUNT(*) as cnt
        FROM scraped_leads GROUP BY category
    """)
    category_stats = {r['category']: r['cnt'] for r in cursor.fetchall()}
    # 各能力域启用源数
    cursor.execute("""
        SELECT COALESCE(category, '') as category, COUNT(*) as cnt
        FROM lead_sources WHERE enabled=1 GROUP BY category
    """)
    source_category_stats = {r['category']: r['cnt'] for r in cursor.fetchall()}
    return jsonify({'code': 200, 'message': 'success',
                    'data': {'status': status_stats, 'enabled_sources': enabled_sources,
                             'avg_score': round(avg_score, 1) if avg_score else 0,
                             'top_assignees': top_assignees,
                             'category_stats': category_stats,
                             'source_category_stats': source_category_stats}})


# ==================== 评估与分配工具函数（与 ai_agent.py 逻辑对齐） ====================

def _load_eval_context(cursor):
    """加载评估上下文：行业成交统计 + 在职销售完整画像（用于科学推荐负责人）。

    销售画像维度（综合分析历史拜访案例、商机情况、合同签订情况）：
    - 工作量：当前活跃商机数、名下客户数
    - 拜访案例：历史拜访次数、已完成拜访数、同行业客户拜访次数
    - 商机情况：活跃商机总金额、推进中（非初期）商机数、商机阶段分布
    - 合同签订：合同总数、合同总金额、已回款金额、同行业合同数
    - 行业经验：曾服务过的行业集合（来自 customers.industry）

    用 user_roles 表查询（支持多角色），不遗漏兼任销售的人员。
    """
    # 行业成交统计（基于合同签订情况，更准确反映行业经验）
    cursor.execute("""
        SELECT industry, COUNT(*) as cnt FROM business
        WHERE status='active' AND industry IS NOT NULL AND industry!=''
        GROUP BY industry
    """)
    industry_stats = {r['industry']: r['cnt'] for r in cursor.fetchall()}

    # 在职销售基础信息 + 工作量（活跃商机数）
    cursor.execute("""
        SELECT u.username, u.name, COUNT(b.id) as biz_count
        FROM users u
        JOIN user_roles ur ON u.username = ur.username AND ur.role='销售'
        LEFT JOIN business b ON b.owner_id = u.username AND b.status='active'
        WHERE u.status='在职' AND u.role NOT IN ('主任', '院长')
        GROUP BY u.username ORDER BY biz_count ASC, RANDOM()
    """)
    salespeople = [dict(r) for r in cursor.fetchall()]
    if not salespeople:
        return industry_stats, salespeople

    usernames = [s['username'] for s in salespeople]
    placeholder = ','.join('?' * len(usernames))

    # 名下客户数 + 各销售所辖客户的行业分布
    cursor.execute(f"""
        SELECT owner_id, COUNT(*) as cust_count
        FROM customers
        WHERE owner_id IN ({placeholder}) AND owner_id IS NOT NULL
        GROUP BY owner_id
    """, usernames)
    cust_counts = {r['owner_id']: r['cust_count'] for r in cursor.fetchall()}

    cursor.execute(f"""
        SELECT owner_id, industry, COUNT(*) as cnt
        FROM customers
        WHERE owner_id IN ({placeholder}) AND owner_id IS NOT NULL
              AND industry IS NOT NULL AND industry != ''
        GROUP BY owner_id, industry
    """, usernames)
    cust_industries = {}  # {username: {industry: count}}
    for r in cursor.fetchall():
        cust_industries.setdefault(r['owner_id'], {})[r['industry']] = r['cnt']

    # 拜访案例统计：总拜访次数 + 已完成拜访次数
    cursor.execute(f"""
        SELECT visitor_id,
               COUNT(*) as visit_total,
               SUM(CASE WHEN status='completed' OR actual_date IS NOT NULL THEN 1 ELSE 0 END) as visit_done
        FROM visits
        WHERE visitor_id IN ({placeholder}) AND visitor_id IS NOT NULL
        GROUP BY visitor_id
    """, usernames)
    visit_stats = {r['visitor_id']: dict(r) for r in cursor.fetchall()}

    # 按行业分组的拜访次数：用于按线索行业精确匹配销售的同行业拜访经验
    cursor.execute(f"""
        SELECT v.visitor_id, c.industry, COUNT(*) as cnt
        FROM visits v
        JOIN customers c ON v.cust_id = c.id
        WHERE v.visitor_id IN ({placeholder}) AND v.visitor_id IS NOT NULL
              AND c.industry IS NOT NULL AND c.industry != ''
        GROUP BY v.visitor_id, c.industry
    """, usernames)
    visit_by_industry = {}  # {username: {industry: count}}
    for r in cursor.fetchall():
        visit_by_industry.setdefault(r['visitor_id'], {})[r['industry']] = r['cnt']

    # 商机情况：活跃商机总金额 + 推进中商机数（非"初期接触/需求确认"阶段）
    cursor.execute(f"""
        SELECT owner_id,
               COUNT(*) as biz_total,
               COALESCE(SUM(amount), 0) as biz_amount,
               SUM(CASE WHEN stage NOT IN ('初期接触', '需求确认', '方案报价') THEN 1 ELSE 0 END) as biz_advanced
        FROM business
        WHERE owner_id IN ({placeholder}) AND owner_id IS NOT NULL AND status='active'
        GROUP BY owner_id
    """, usernames)
    biz_stats = {r['owner_id']: dict(r) for r in cursor.fetchall()}

    # 商机按行业分组：用于按线索行业精确匹配销售的同行业商机经验
    cursor.execute(f"""
        SELECT owner_id, industry, COUNT(*) as cnt, COALESCE(SUM(amount), 0) as amt
        FROM business
        WHERE owner_id IN ({placeholder}) AND owner_id IS NOT NULL
              AND status='active' AND industry IS NOT NULL AND industry != ''
        GROUP BY owner_id, industry
    """, usernames)
    biz_by_industry = {}  # {username: {industry: {'count': n, 'amount': amt}}}
    for r in cursor.fetchall():
        biz_by_industry.setdefault(r['owner_id'], {})[r['industry']] = {
            'count': r['cnt'], 'amount': float(r['amt'] or 0)
        }

    # 合同签订情况：合同数 + 合同总金额 + 已回款金额
    cursor.execute(f"""
        SELECT owner_id,
               COUNT(*) as contract_total,
               COALESCE(SUM(total_amt), 0) as contract_amount,
               COALESCE(SUM(paid_amt), 0) as paid_amount
        FROM contracts
        WHERE owner_id IN ({placeholder}) AND owner_id IS NOT NULL
        GROUP BY owner_id
    """, usernames)
    contract_stats = {r['owner_id']: dict(r) for r in cursor.fetchall()}

    # 合同按行业分组：用于按线索行业精确匹配销售的同行业签约经验
    cursor.execute(f"""
        SELECT ct.owner_id, c.industry,
               COUNT(*) as cnt, COALESCE(SUM(ct.total_amt), 0) as amt
        FROM contracts ct
        JOIN customers c ON ct.cust_id = c.id
        WHERE ct.owner_id IN ({placeholder}) AND ct.owner_id IS NOT NULL
              AND c.industry IS NOT NULL AND c.industry != ''
        GROUP BY ct.owner_id, c.industry
    """, usernames)
    contract_by_industry = {}  # {username: {industry: {'count': n, 'amount': amt}}}
    for r in cursor.fetchall():
        contract_by_industry.setdefault(r['owner_id'], {})[r['industry']] = {
            'count': r['cnt'], 'amount': float(r['amt'] or 0)
        }

    # 组装销售画像
    for s in salespeople:
        u = s['username']
        s['cust_count'] = cust_counts.get(u, 0)
        s['industries_served'] = cust_industries.get(u, {})
        vs = visit_stats.get(u, {})
        s['visit_total'] = vs.get('visit_total', 0)
        s['visit_done'] = vs.get('visit_done', 0)
        s['visit_by_industry'] = visit_by_industry.get(u, {})
        bs = biz_stats.get(u, {})
        s['biz_amount'] = float(bs.get('biz_amount', 0) or 0)
        s['biz_advanced'] = bs.get('biz_advanced', 0) or 0
        s['biz_by_industry'] = biz_by_industry.get(u, {})
        cs = contract_stats.get(u, {})
        s['contract_total'] = cs.get('contract_total', 0)
        s['contract_amount'] = float(cs.get('contract_amount', 0) or 0)
        s['paid_amount'] = float(cs.get('paid_amount', 0) or 0)
        s['contract_by_industry'] = contract_by_industry.get(u, {})

    # —— 知识库知识画像（纯 DB，无 LLM）——
    kb_profiles = _build_knowledge_profiles(cursor, usernames)
    for s in salespeople:
        pf = kb_profiles.get(s['username'], {
            'doc_count': 0, 'type_counts': {}, 'industries': {},
            'customers': set(), 'success_case_count': 0, 'keyword_bag': set(),
        })
        # JSON 安全：把 set 转 list（打分时会按需重新转 set）
        s['kb'] = {
            'doc_count': pf.get('doc_count', 0),
            'type_counts': pf.get('type_counts', {}),
            'industries': pf.get('industries', {}),
            'customers': sorted(pf.get('customers', set()) or []),
            'success_case_count': pf.get('success_case_count', 0),
            'keyword_bag': sorted(pf.get('keyword_bag', set()) or []),
        }

    return industry_stats, salespeople


def _tokenize_keywords(text):
    """简易中文关键词提取：按标点/空白分词，再加中文二元切分，返回小写去重集合。
    不依赖 jieba，纯标准库实现，保证离线可用。"""
    if not text:
        return set()
    import re
    s = str(text).lower()
    # 中英文单词/数字 + 中文二元
    words = set(re.findall(r'[a-zA-Z0-9\u4e00-\u9fff]{2,}', s))
    # 中文二元
    ch_only = re.sub(r'[^\u4e00-\u9fff]', '', s)
    for i in range(len(ch_only) - 1):
        words.add(ch_only[i:i+2])
    return words


def _build_knowledge_profiles(cursor, usernames):
    """基于知识库为每个销售构建知识画像（纯 DB，不调用 LLM，离线可用）。

    返回 {username: {
        'doc_count': n,                   # 拥有文档总数（知识深度）
        'type_counts': {doc_type: n},     # 各类型文档数
        'industries': {industry: n},      # 覆盖行业（来自文档关联客户→industry）
        'customers': set,                 # 客户名称集合（customer_info→cust_id→name）
        'success_case_count': n,          # 成功案例数（合同类文档+「中标/签约/成功」关键词文档）
        'keyword_bag': set,               # 关键词集合（title+summary+tags）
    }}
    """
    profiles = {u: {
        'doc_count': 0,
        'type_counts': {},
        'industries': {},
        'customers': set(),
        'success_case_count': 0,
        'keyword_bag': set(),
    } for u in usernames}
    if not usernames:
        return profiles
    placeholder = ','.join('?' * len(usernames))

    # 1) 所有销售名下的知识文档
    cursor.execute(f"""
        SELECT d.id, d.owner_id, d.doc_type, d.title, d.summary, d.tags, d.cust_id
        FROM knowledge_documents d
        WHERE d.owner_id IN ({placeholder})
    """, usernames)
    docs = cursor.fetchall()

    # 2) cust_id → industry/name 映射（一次查询，避免 N+1）
    cust_ids = sorted({d['cust_id'] for d in docs if d['cust_id']})
    cust_map = {}
    if cust_ids:
        cph = ','.join('?' * len(cust_ids))
        cursor.execute(f"""
            SELECT id, name, industry FROM customers WHERE id IN ({cph})
        """, cust_ids)
        for cr in cursor.fetchall():
            cust_map[cr['id']] = {'name': cr['name'] or '', 'industry': cr['industry'] or ''}

    SUCCESS_DOC_TYPES = {'contract', 'bid_document'}
    SUCCESS_KW = ('中标', '签约', '签订', '成单', '验收', '回款', '交付', '合作达成')

    for d in docs:
        u = d['owner_id']
        if u not in profiles:
            continue
        pf = profiles[u]
        dtype = d['doc_type'] or 'other'
        pf['doc_count'] += 1
        pf['type_counts'][dtype] = pf['type_counts'].get(dtype, 0) + 1

        # 关键词袋：title + summary + tags
        bag_source = ' '.join(x for x in (d['title'], d['summary'], d['tags']) if x)
        for kw in _tokenize_keywords(bag_source):
            pf['keyword_bag'].add(kw)

        # 行业/客户：从 cust_id 关联
        cid = d['cust_id']
        if cid and cid in cust_map:
            cname = cust_map[cid]['name']
            cind = cust_map[cid]['industry']
            if cname:
                pf['customers'].add(cname.strip())
                for kw in _tokenize_keywords(cname):
                    pf['keyword_bag'].add(kw)
            if cind:
                pf['industries'][cind] = pf['industries'].get(cind, 0) + 1
                for kw in _tokenize_keywords(cind):
                    pf['keyword_bag'].add(kw)

        # 成功案例：合同/投标类文档 OR 标题含中标/签约等关键词
        is_success = dtype in SUCCESS_DOC_TYPES or any(
            kw in (d['title'] or '') or kw in (d['summary'] or '') for kw in SUCCESS_KW
        )
        if is_success:
            pf['success_case_count'] += 1

    # 3) 知识图谱增强：若 person 实体匹配销售姓名，拉取其关联行业/客户/项目实体
    cursor.execute(f"""
        SELECT u.username, u.name FROM users u
        WHERE u.username IN ({placeholder})
    """, usernames)
    name_to_user = {}
    for r in cursor.fetchall():
        name_to_user[r['name'] or ''] = r['username']
        name_to_user[r['username']] = r['username']

    if name_to_user:
        person_names = [n for n in name_to_user.keys() if n]
        if person_names:
            pph = ','.join('?' * len(person_names))
            cursor.execute(f"""
                SELECT id, name FROM knowledge_entities
                WHERE entity_type='person' AND name IN ({pph})
            """, person_names)
            person_ents = {r['id']: r['name'] for r in cursor.fetchall()}

            if person_ents:
                pids = list(person_ents.keys())
                pid_ph = ','.join('?' * len(pids))
                cursor.execute(f"""
                    SELECT r.source_id, r.target_id, r.relation_type,
                           e.name as target_name, e.entity_type as target_type
                    FROM knowledge_relations r
                    JOIN knowledge_entities e ON r.target_id = e.id
                    WHERE r.source_id IN ({pid_ph})
                """, pids)
                for rel in cursor.fetchall():
                    src_name = person_ents.get(rel['source_id'], '')
                    u = name_to_user.get(src_name)
                    if not u or u not in profiles:
                        continue
                    pf = profiles[u]
                    tname = rel['target_name'] or ''
                    ttype = rel['target_type'] or ''
                    if not tname:
                        continue
                    if ttype == 'organization' and len(tname) <= 6:
                        pf['industries'][tname] = pf['industries'].get(tname, 0) + 1
                    if ttype in ('customer', 'organization'):
                        pf['customers'].add(tname.strip())
                    if ttype in ('project', 'contract', 'business'):
                        pf['success_case_count'] += 1
                    for kw in _tokenize_keywords(tname):
                        pf['keyword_bag'].add(kw)

                cursor.execute(f"""
                    SELECT r.source_id, r.target_id, r.relation_type,
                           e.name as source_name, e.entity_type as source_type
                    FROM knowledge_relations r
                    JOIN knowledge_entities e ON r.source_id = e.id
                    WHERE r.target_id IN ({pid_ph})
                """, pids)
                for rel in cursor.fetchall():
                    tgt_name = person_ents.get(rel['target_id'], '')
                    u = name_to_user.get(tgt_name)
                    if not u or u not in profiles:
                        continue
                    pf = profiles[u]
                    sname = rel['source_name'] or ''
                    stype = rel['source_type'] or ''
                    if not sname:
                        continue
                    if stype in ('customer', 'organization'):
                        pf['customers'].add(sname.strip())
                    if stype in ('project', 'contract', 'business'):
                        pf['success_case_count'] += 1
                    for kw in _tokenize_keywords(sname):
                        pf['keyword_bag'].add(kw)

    return profiles


def _semantic_knowledge_boost(lead, username_list):
    """可选 LLM 增强：用语义搜索把线索与知识库匹配，按 owner_id 聚合相似度。
    返回 {username: score_0_to_1}；失败返回空 dict（调用方自动降级为关键词匹配）。"""
    try:
        from vector_search import semantic_search
    except Exception:
        return {}
    opp = (lead.get('opportunity_name') or '').strip()
    company = (lead.get('company') or '').strip()
    industry = (lead.get('industry') or '').strip()
    region = (lead.get('region') or '').strip()
    category = (lead.get('category') or '').strip()
    query = f"{category} {industry} {region} {company} {opp}".strip()
    if not query:
        return {}
    try:
        matches = semantic_search(query, top_k=10)
    except Exception:
        return {}
    if not matches:
        return {}
    doc_ids = sorted({m['doc_id'] for m in matches if m.get('doc_id')})
    if not doc_ids:
        return {}
    try:
        from extensions import get_db
        conn = get_db()
        cur = conn.cursor()
        dph = ','.join('?' * len(doc_ids))
        cur.execute(f"SELECT id, owner_id FROM knowledge_documents WHERE id IN ({dph})", doc_ids)
        doc_owner = {r['id']: r['owner_id'] for r in cur.fetchall() if r['owner_id']}
    except Exception:
        return {}
    owner_best = {}
    for m in matches:
        oid = doc_owner.get(m.get('doc_id'))
        if not oid or oid not in username_list:
            continue
        sim = float(m.get('similarity') or 0)
        if sim > owner_best.get(oid, 0):
            owner_best[oid] = sim
    if not owner_best:
        return {}
    mx = max(owner_best.values()) or 1
    return {u: min(1.0, v / mx) for u, v in owner_best.items()}


def _evaluate_lead(lead, industry_stats):
    """结合历史数据评估线索意向分值，按能力域类别应用专属评分逻辑。

    五大能力域专属评分：
    - 电商商机：采用抓取阶段计算的爆款评分(ecommerce_score)，高需求低竞争为佳
    - 舆情痛点：采用痛点评分(sentiment_score)，痛点词越多意向越高（未满足需求=商机）
    - 竞品情报：检测促销/价格变动，促销活动指示市场机会
    - 企业客源：新注册企业=潜在采购需求，按行业成交加分
    - 招投标监控/RSS抓取：原有规则评分（行业成交+来源渠道+强意向关键词）
    """
    category = (lead.get('category') or '').strip()
    raw = _parse_config(lead.get('raw_data'))
    score = 50
    reasons = []
    industry = (lead.get('industry') or '').strip()

    # —— AI 智能体搜索线索：优先用 LLM 提供的 intent_score，叠加军工领域加权 ——
    if raw.get('source_type') == 'ai_search' and raw.get('intent_score') is not None:
        score = max(0, min(100, int(raw.get('intent_score', 50))))
        intent = raw.get('intent', '')
        opp_name = (lead.get('opportunity_name') or '').strip()
        if intent:
            reasons.append(intent)
        # 军采监控专属加权（军工采购商机价值最高）
        if category == '军采监控':
            score = min(100, score + 10)
            reasons.append('军采监控商机，采购意向明确')
            # 军采白名单链接加分（plap.cn/weain.mil.cn 等真实军采域名）
            link = (lead.get('link') or '').lower()
            if any(d in link for d in _MILITARY_WHITELIST):
                score = min(100, score + 8)
                reasons.append('来源为军采官方网站，可信度高')
            # 公告类型/采购方式加分
            procurement_method = raw.get('procurement_method', '')
            method_bonus = {'公开招标': 5, '邀请招标': 4, '竞争性谈判': 3, '询价': 2, '单一来源': 2}
            if procurement_method in method_bonus:
                score = min(100, score + method_bonus[procurement_method])
                reasons.append(f'采购方式：{procurement_method}')
            # 时效性：仍在投标有效期加分，已过截止日期降分
            deadline = raw.get('deadline', '')
            publish_date = raw.get('publish_date', '')
            today = datetime.now().strftime('%Y-%m-%d')
            if deadline:
                if deadline >= today:
                    score = min(100, score + 5)
                    reasons.append(f'投标截止 {deadline}，仍可参与')
                else:
                    score = max(0, score - 15)
                    reasons.append(f'投标已截止（{deadline}），意向降低')
            elif publish_date:
                reasons.append(f'发布日期 {publish_date}')
        # 9大业务领域匹配加分（命中用户关注领域额外加分）
        domain = _match_military_domain(opp_name + ' ' + intent)
        if domain:
            score = min(100, score + 5)
            reasons.append(f'命中本公司业务领域：{domain}')
        # 行业成交加分
        if industry and industry in industry_stats:
            score = min(100, score + min(10, industry_stats[industry]))
            reasons.append(f'行业「{industry}」有历史成交基础')
        if not reasons:
            reasons.append('AI智能体搜索评估')
        return score, '；'.join(reasons)

    # —— 能力域专属评分 ——
    if category == '电商商机' and raw.get('ecommerce_score') is not None:
        # 电商爆款评分作为基础分
        score = int(raw.get('ecommerce_score', 50))
        reasons.append(raw.get('reason', '电商爆款评分'))
        if industry and industry in industry_stats:
            score = min(100, score + min(10, industry_stats[industry]))
            reasons.append(f'行业「{industry}」有历史成交基础')
        return max(0, min(100, score)), '；'.join(reasons) if reasons else '电商爆款评分'

    if category == '舆情痛点' and raw.get('sentiment_score') is not None:
        # 痛点评分作为基础分：用户痛点=未满足需求=商机
        score = int(raw.get('sentiment_score', 50))
        pain_type = raw.get('pain_type', '')
        pain_count = raw.get('pain_count', 0)
        opp_count = raw.get('opp_count', 0)
        reasons.append(f'{pain_type}：命中{pain_count}个痛点词+{opp_count}个商机词')
        if opp_count > 0:
            score = min(100, score + 10)
            reasons.append('含明确商机关键词，转化潜力高')
        return max(0, min(100, score)), '；'.join(reasons) if reasons else '舆情痛点评分'

    if category == '竞品情报':
        # 竞品促销/新品=市场机会信号
        promo = raw.get('promo', '')
        if promo:
            score += 20
            reasons.append(f'竞品有「{promo}」动态，市场机会窗口期')
        else:
            reasons.append('竞品常规动态，持续监控')
        if industry and industry in industry_stats:
            score += min(10, industry_stats[industry])
            reasons.append(f'行业「{industry}」有历史成交')
        score = max(0, min(100, score))
        return score, '；'.join(reasons) if reasons else '竞品情报监控'

    if category == '企业客源':
        # 新注册企业=潜在采购需求
        reasons.append('新注册企业，潜在采购需求待挖掘')
        if industry and industry in industry_stats:
            score += min(20, industry_stats[industry] * 2)
            reasons.append(f'行业「{industry}」历史成交{industry_stats[industry]}单，意向较高')
        score = max(0, min(100, score))
        return score, '；'.join(reasons)

    # —— 默认评分（招投标监控/RSS抓取/API接口/手动导入）：原有规则 ——
    if industry and industry in industry_stats:
        score += min(20, industry_stats[industry] * 2)
        reasons.append(f'行业「{industry}」历史成交{industry_stats[industry]}单，意向较高')
    elif industry:
        reasons.append(f'行业「{industry}」历史成交较少，需进一步培育')
    source = (lead.get('source') or '').strip()
    source_bonus = {'主动咨询': 25, '老客户介绍': 20, '展会': 15, '官网': 10, '官网咨询': 10,
                    '外部抓取': 5, 'RSS抓取': 5, 'API接口': 5, '招投标监控': 15, '电商商机': 10,
                    '企业客源': 10, '竞品情报': 8, '舆情痛点': 8}
    if source in source_bonus:
        score += source_bonus[source]
        reasons.append(f'来源「{source}」为高价值渠道')
    remark = (lead.get('remark') or '').strip()
    strong_kw = ['急需', '预算', '招标', '采购', '计划', '立项']
    if any(k in remark for k in strong_kw):
        score += 15
        reasons.append('备注含强意向关键词')
    score = max(0, min(100, score))
    if not reasons:
        reasons.append('信息有限，建议人工跟进核实')
    return score, '；'.join(reasons)


# ==================== 图片OCR批量导入线索 ====================

_ocr_instance = None


def _get_ocr():
    """懒加载 PaddleOCR 实例（首次调用时加载模型，后续复用）。

    模型文件自动下载到 vendor/paddleocr/whl/ 下。如果网络不可达，
    需提前将 det/rec/cls 三个模型目录放入对应路径。
    """
    global _ocr_instance
    if _ocr_instance is None:
        import os
        import sys
        vendor = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vendor')
        if os.path.isdir(vendor) and vendor not in sys.path:
            sys.path.insert(0, vendor)
        # Windows DLL 搜索路径：paddlepaddle 的 C 扩展依赖 paddle/libs/*.dll
        paddle_libs = os.path.join(vendor, 'paddle', 'libs')
        if os.path.isdir(paddle_libs):
            os.add_dll_directory(paddle_libs)
        try:
            from paddleocr import PaddleOCR
            # 指定模型存储路径，避免写到用户目录
            whl_dir = os.path.join(vendor, 'paddleocr', 'whl')
            os.makedirs(whl_dir, exist_ok=True)
            _ocr_instance = PaddleOCR(
                use_angle_cls=True, lang='ch', show_log=False,
                det_model_dir=os.path.join(whl_dir, 'det', 'ch'),
                rec_model_dir=os.path.join(whl_dir, 'rec', 'ch'),
                cls_model_dir=os.path.join(whl_dir, 'cls'),
            )
            print("[OCR] PaddleOCR 加载成功")
        except Exception as e:
            print(f"[OCR] PaddleOCR 加载失败: {e}")
            raise
    return _ocr_instance


def _ocr_image(image_path):
    """对单张图片执行OCR，返回 (拼接后的纯文本, None) 或 (空字符串, 错误信息)。"""
    try:
        ocr = _get_ocr()
        result = ocr.ocr(image_path, cls=True)
        if not result or not result[0]:
            return '', None
        lines = []
        for line in result[0]:
            text = line[1][0] if line[1] and len(line[1]) > 0 else ''
            if text:
                lines.append(text.strip())
        return '\n'.join(lines), None
    except Exception as e:
        err_msg = str(e)
        print(f"[OCR] 图片识别失败: {err_msg}")
        return '', err_msg


def _llm_parse_lead_text(raw_text):
    """用LLM将OCR文本解析为结构化线索字段。"""
    if not raw_text or not raw_text.strip():
        return {}
    try:
        from config import LLM_API_KEY, LLM_API_BASE, LLM_MODEL, USE_LLM
        if not USE_LLM:
            return {}
        prompt = """从以下图片OCR识别文本中提取线索信息，返回JSON格式。

文本内容：
{raw_text}

请提取以下字段（无法识别的留空字符串）：
{{
  "company": "公司/招标单位名称",
  "opportunity_name": "商机名称/项目标题/招标项目名称",
  "contact_name": "联系人姓名",
  "phone": "联系电话",
  "email": "电子邮箱",
  "industry": "行业",
  "region": "地区/区域",
  "link": "链接URL（如有）",
  "remark": "备注/其他说明",
  "tender_no": "招标编号",
  "budget": "预算金额（保留原始文本）",
  "deadline": "截止日期（YYYY-MM-DD格式）",
  "publish_date": "发布日期（YYYY-MM-DD格式）",
  "agency": "招标代理机构",
  "agency_phone": "代理机构电话"
}}

注意：只返回JSON，不要添加任何额外文字。日期统一转为YYYY-MM-DD格式。"""
        import requests
        headers = {
            'Authorization': f'Bearer {LLM_API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': LLM_MODEL,
            'messages': [
                {'role': 'system', 'content': '你是专业的信息提取助手。请严格按照JSON格式返回结果，不要输出思考过程或额外文字。'},
                {'role': 'user', 'content': prompt.format(raw_text=raw_text[:6000])}
            ],
            'temperature': 0.1,
            'max_tokens': 180000
        }
        try:
            payload['extra_body'] = {'chat_template_kwargs': {'enable_thinking': False}}
        except Exception:
            pass
        response = requests.post(
            f'{LLM_API_BASE}/chat/completions',
            headers=headers,
            json=payload,
            timeout=60
        )
        if response.status_code == 200:
            data = response.json()
            content = data['choices'][0]['message'].get('content')
            if content and content.strip():
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    return json.loads(json_match.group())
        else:
            print(f"[OCR-LLM] HTTP {response.status_code}")
    except Exception as e:
        print(f"[OCR-LLM] 解析失败: {e}")
    return {}


@leads_bp.route('/api/leads/ocr-images', methods=['POST'])
@token_required
def ocr_import_images():
    """批量上传图片，OCR识别文字后用LLM解析为结构化线索字段，返回预览数据。"""
    import os
    import tempfile

    files = request.files.getlist('images')
    if not files:
        return jsonify({'code': 400, 'message': '请选择图片文件', 'data': None})

    results = []
    ocr_init_error = None
    for f in files:
        if not f or not f.filename:
            continue
        filename = f.filename
        suffix = os.path.splitext(filename)[1].lower()
        if suffix not in ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'):
            results.append({
                'image_name': filename, 'raw_text': '', 'parsed': {},
                'error': '不支持的图片格式'
            })
            continue
        # 只保留已白名单校验的后缀，其余部分用随机串替代，防止文件名路径穿越
        tmp_path = os.path.join(tempfile.gettempdir(), f'ocr_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}{suffix}')
        try:
            f.save(tmp_path)
            raw_text, ocr_err = _ocr_image(tmp_path)
            if ocr_err and not raw_text:
                # OCR 引擎级别的错误（如模型加载失败）
                if ocr_init_error is None:
                    ocr_init_error = ocr_err
                results.append({
                    'image_name': filename, 'raw_text': '', 'parsed': {},
                    'error': f'OCR识别引擎错误: {ocr_err}'
                })
                continue
            if not raw_text:
                results.append({
                    'image_name': filename, 'raw_text': '', 'parsed': {},
                    'error': '未识别到文字'
                })
                continue
            parsed = _llm_parse_lead_text(raw_text)
            results.append({
                'image_name': filename, 'raw_text': raw_text, 'parsed': parsed
            })
        except Exception as e:
            results.append({
                'image_name': filename, 'raw_text': '', 'parsed': {},
                'error': str(e)
            })
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    # 如果所有图片都因 OCR 引擎错误失败，返回 500
    if ocr_init_error and all(r.get('error', '').startswith('OCR识别引擎错误') for r in results if r.get('error')):
        return jsonify({
            'code': 500,
            'message': f'OCR引擎初始化失败: {ocr_init_error}',
            'data': {'results': results, 'total': len(results)}
        })

    return jsonify({'code': 200, 'message': 'success',
                    'data': {'results': results, 'total': len(results)}})


@leads_bp.route('/api/leads/ocr-images/execute', methods=['POST'])
@token_required
def ocr_import_execute():
    """确认导入OCR解析后的线索数据。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    leads = data.get('leads') or data.get('rows') or []
    if not leads:
        return jsonify({'code': 400, 'message': '无有效数据', 'data': None})

    db = get_db()
    cursor = db.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    success_count = 0
    fail_count = 0

    for lead in leads:
        company = (lead.get('company') or '').strip()
        if not company:
            fail_count += 1
            continue
        opp_name = (lead.get('opportunity_name') or '').strip()
        link = (lead.get('link') or '').strip()
        dup = False
        if link:
            cursor.execute("SELECT id FROM scraped_leads WHERE link=?", (link,))
            if cursor.fetchone():
                dup = True
        if not dup and opp_name and company:
            cursor.execute(
                "SELECT id FROM scraped_leads WHERE opportunity_name=? AND company=?",
                (opp_name, company)
            )
            if cursor.fetchone():
                dup = True
        if dup:
            fail_count += 1
            continue
        try:
            cursor.execute("""
                INSERT INTO scraped_leads (company, opportunity_name, contact_name, phone, email,
                                           industry, region, source, link, remark,
                                           tender_no, budget, deadline, publish_date,
                                           agency, agency_phone,
                                           status, category, scraped_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', '图片导入', ?, ?)
            """, (
                company, opp_name,
                lead.get('contact_name', ''), lead.get('phone', ''),
                lead.get('email', ''), lead.get('industry', ''),
                lead.get('region', ''), '图片导入',
                link, lead.get('remark', ''),
                lead.get('tender_no', ''), lead.get('budget', ''),
                lead.get('deadline', ''), lead.get('publish_date', ''),
                lead.get('agency', ''), lead.get('agency_phone', ''),
                now, now
            ))
            success_count += 1
        except Exception:
            fail_count += 1

    db.commit()
    if success_count > 0:
        record_operation_log(payload['username'], '导入', '线索(图片OCR)',
                             f'图片OCR导入线索：成功{success_count}条，失败{fail_count}条')

    return jsonify({
        'code': 200, 'message': '导入完成',
        'data': {
            'total': len(leads),
            'success_count': success_count,
            'fail_count': fail_count
        }
    })


def _assign_lead(lead, salespeople):
    """基于销售人员历史拜访案例、商机情况、合同签订 + 知识库，多维度评分推荐科学负责人。

    评分维度（满分100）：
    1. 行业匹配度（26分）：同行业合同/商机/拜访/客户综合（历史对接经验）
    2. 历史业绩（22分）：合同总金额 + 已回款金额 + 回款率
    3. 商机推进能力（13分）：活跃商机数 + 推进中商机占比 + 商机总金额
    4. 拜访经验（13分）：历史拜访次数 + 已完成拜访数
    5. 当前工作量（8分）：活跃商机越少越空闲得分越高（避免过载）
    6. 区域匹配（3分）：名下同区域客户加分
    7. 知识库匹配（15分）：知识深度 + 行业/客户/关键词知识画像吻合 + 语义搜索命中 + 成功案例数

    返回：{username, name, reason, details}，details 含各维度分数便于前端展示。
    """
    if not salespeople:
        return None

    industry = (lead.get('industry') or '').strip()
    region = (lead.get('region') or '').strip()
    usernames = [s['username'] for s in salespeople]

    # 计算全局最大值用于归一化（避免单一指标极端值主导）
    max_contract_amount = max((s.get('contract_amount', 0) for s in salespeople), default=1) or 1
    max_paid_amount = max((s.get('paid_amount', 0) for s in salespeople), default=1) or 1
    max_biz_amount = max((s.get('biz_amount', 0) for s in salespeople), default=1) or 1
    max_visit_total = max((s.get('visit_total', 0) for s in salespeople), default=1) or 1
    max_biz_count = max((s.get('biz_count', 0) for s in salespeople), default=1) or 1
    max_cust_count = max((s.get('cust_count', 0) for s in salespeople), default=1) or 1
    max_kb_docs = max((s.get('kb', {}).get('doc_count', 0) for s in salespeople), default=1) or 1
    max_kb_cases = max((s.get('kb', {}).get('success_case_count', 0) for s in salespeople), default=1) or 1

    # —— 知识库信号 1/2：语义搜索命中（LLM，失败降级为空）——
    semantic_boosts = _semantic_knowledge_boost(lead, usernames)

    # —— 知识库信号 2/2：线索关键词袋（合同/商机/客户/区域/机会名拼接 → 二元+单词）——
    company = (lead.get('company') or '').strip()
    opp_name = (lead.get('opportunity_name') or '').strip()
    category = (lead.get('category') or '').strip()
    raw = lead.get('raw_data') or ''
    if isinstance(raw, str):
        try:
            import json as _json
            raw_d = _json.loads(raw)
        except Exception:
            raw_d = {}
    else:
        raw_d = raw if isinstance(raw, dict) else {}
    extra_kw = raw_d.get('keywords') or raw_d.get('tags') or raw_d.get('intent') or ''
    lead_query_parts = [industry, region, company, opp_name, category, str(extra_kw)]
    lead_keywords = _tokenize_keywords(' '.join(x for x in lead_query_parts if x))

    scored = []
    for s in salespeople:
        reasons = []
        kb = s.get('kb') or {}

        # 1) 行业匹配度（26分）—— 同行业合同/商机/拜访/客户综合
        industry_score = 0.0
        if industry:
            same_industry_contracts = s.get('contract_by_industry', {}).get(industry, {}).get('count', 0)
            same_industry_contract_amt = s.get('contract_by_industry', {}).get(industry, {}).get('amount', 0)
            same_industry_biz = s.get('biz_by_industry', {}).get(industry, {}).get('count', 0)
            same_industry_visits = s.get('visit_by_industry', {}).get(industry, 0)
            same_industry_custs = s.get('industries_served', {}).get(industry, 0)
            industry_score += min(13, same_industry_contracts * 4.5)
            if same_industry_contracts > 0:
                reasons.append(f'同行业已签{same_industry_contracts}份合同'
                               f'（金额{same_industry_contract_amt:.2f}元）')
            industry_score += min(7, same_industry_biz * 2)
            if same_industry_biz > 0:
                reasons.append(f'同行业有{same_industry_biz}个在推进商机')
            industry_score += min(3, same_industry_visits)
            if same_industry_visits > 0:
                reasons.append(f'同行业客户拜访{same_industry_visits}次')
            industry_score += min(3, same_industry_custs)
            if same_industry_contracts == 0 and same_industry_biz == 0 \
                    and same_industry_visits == 0 and same_industry_custs == 0:
                reasons.append(f'暂无「{industry}」行业服务经验')
        else:
            industry_score = 7.0
            reasons.append('线索未标注行业，行业匹配维度按基础分计算')

        # 2) 历史业绩（22分）—— 合同金额 + 回款 + 回款率
        contract_amount = s.get('contract_amount', 0)
        paid_amount = s.get('paid_amount', 0)
        contract_total = s.get('contract_total', 0)
        performance_score = (contract_amount / max_contract_amount) * 13
        performance_score += (paid_amount / max_paid_amount) * 6
        if contract_amount > 0:
            paid_rate = paid_amount / contract_amount
            if paid_rate >= 0.8:
                performance_score += 3
                reasons.append(f'回款率{paid_rate*100:.1f}%，资金回笼优秀')
            elif paid_rate >= 0.5:
                performance_score += 1.5
        if contract_total > 0:
            reasons.append(f'累计签订{contract_total}份合同，金额{contract_amount:.2f}元')
        else:
            reasons.append('暂无合同签订记录')
        performance_score = min(22, performance_score)

        # 3) 商机推进能力（13分）—— 推进中商机 + 商机金额
        biz_count = s.get('biz_count', 0)
        biz_advanced = s.get('biz_advanced', 0)
        biz_amount = s.get('biz_amount', 0)
        biz_score = 0.0
        if biz_count > 0:
            advance_ratio = biz_advanced / biz_count
            biz_score += min(7, advance_ratio * 9)
            biz_score += min(6, (biz_amount / max_biz_amount) * 6)
            reasons.append(f'活跃商机{biz_count}个（推进中{biz_advanced}个），商机金额{biz_amount:.2f}元')
        else:
            reasons.append('当前无活跃商机，可专注新线索')

        # 4) 拜访经验（13分）—— 拜访次数 + 完成率
        visit_total = s.get('visit_total', 0)
        visit_done = s.get('visit_done', 0)
        visit_score = (visit_total / max_visit_total) * 10.5
        if visit_total > 0:
            done_rate = visit_done / visit_total
            visit_score += min(2.5, done_rate * 2.5)
            reasons.append(f'累计拜访{visit_total}次（已完成{visit_done}次）')
        else:
            reasons.append('暂无历史拜访记录')

        # 5) 当前工作量（8分）—— 商机越少越空闲
        workload_score = max(0, 8 - (biz_count / max_biz_count) * 8)
        if biz_count >= 10:
            reasons.append(f'当前商机{biz_count}个，工作量饱和')
        elif biz_count >= 5:
            reasons.append(f'当前商机{biz_count}个，工作量适中')
        else:
            reasons.append(f'当前商机{biz_count}个，时间充裕')

        # 6) 区域匹配（3分）
        region_score = 0.0
        if region:
            region_score = min(3, (s.get('cust_count', 0) / max_cust_count) * 3)
        else:
            region_score = 1.5

        # 7) 知识库匹配（15分）—— 深度/行业/客户/关键词+语义+成功案例
        kb_score = 0.0
        kb_reasons = []

        # 7.1 知识深度（3分）：拥有的知识文档总数归一化
        kb_docs = kb.get('doc_count', 0)
        depth_sub = (kb_docs / max_kb_docs) * 3 if max_kb_docs else 0
        kb_score += depth_sub
        if kb_docs > 0:
            type_counts = kb.get('type_counts', {})
            types_cn = []
            _DOC_CN = {'visit_summary': '拜访纪要', 'contract': '合同',
                       'bid_document': '投标', 'technical_plan': '技术方案',
                       'customer_info': '客户资料', 'industry_report': '行业报告',
                       'meeting_minutes': '会议纪要', 'personnel_qualification': '人员资质',
                       'company_qualification': '企业资质', 'other': '其他'}
            for dt, cnt in sorted(type_counts.items(), key=lambda x: -x[1])[:3]:
                types_cn.append(f"{_DOC_CN.get(dt, dt)}{cnt}")
            if types_cn:
                kb_reasons.append(f"知识文档{kb_docs}篇：{'/'.join(types_cn)}")

        # 7.2 行业匹配（4分）：知识库中是否有相关行业记录
        if industry:
            kb_industries = kb.get('industries', {})
            if isinstance(kb_industries, dict):
                kb_industry_hits = kb_industries.get(industry, 0)
                # 也用关键词袋查行业关键词
                ind_kw = _tokenize_keywords(industry)
                kb_bag = set(kb.get('keyword_bag', []) or [])
                overlap_kw = len(ind_kw & kb_bag)
                ind_kw_score = min(2.0, overlap_kw / max(len(ind_kw), 1) * 2)
                ind_match_sub = min(2.0, kb_industry_hits)  # 直接行业名命中
                kb_score += min(4.0, ind_match_sub + ind_kw_score)
                if kb_industry_hits > 0 or overlap_kw > 0:
                    kb_reasons.append(f"知识库记录过{industry}相关经验")
                # 无知识命中不给负分（没文档不代表无经验，只在有命中时加分）

        # 7.3 客户匹配（2分）：知识库中是否有该招标单位/客户的资料
        if company:
            kb_customers = set(kb.get('customers', []) or [])
            company_match = 0
            if company in kb_customers:
                company_match += 1
            comp_kw = _tokenize_keywords(company)
            kb_bag = set(kb.get('keyword_bag', []) or [])
            comp_overlap = len(comp_kw & kb_bag)
            company_match += min(1, comp_overlap / max(len(comp_kw), 1))
            c_sub = min(2.0, company_match)
            kb_score += c_sub
            if c_sub > 0:
                kb_reasons.append(f"知识库包含「{company}」相关资料")

        # 7.4 线索关键词与知识关键词袋相似度（2分）
        if lead_keywords:
            kb_bag = set(kb.get('keyword_bag', []) or [])
            overlap = len(lead_keywords & kb_bag)
            union_val = len(lead_keywords | kb_bag) or 1
            jaccard = overlap / union_val
            kw_sub = min(2.0, jaccard * 20)  # 放缩到 0-2
            kb_score += kw_sub
            if overlap >= 3:
                kb_reasons.append(f"关键词匹配{overlap}个：商机内容高度吻合")

        # 7.5 语义搜索命中增强（LLM，有则加）
        sem = semantic_boosts.get(s['username'], 0)
        if sem > 0:
            sem_sub = min(2.0, sem * 2)
            kb_score += sem_sub
            if sem >= 0.5:
                kb_reasons.append("语义搜索命中相关知识文档")

        # 7.6 成功案例相关知识数（2分）：合同/中标/签约文档 → 可复制成功经验
        kb_cases = kb.get('success_case_count', 0)
        case_sub = min(2.0, (kb_cases / max_kb_cases) * 2) if max_kb_cases else 0
        kb_score += case_sub
        if kb_cases > 0:
            kb_reasons.append(f"知识库沉淀{kb_cases}个成功案例")

        kb_score = min(15.0, kb_score)
        if not kb_reasons and kb_score < 1:
            kb_reasons.append("知识库暂未积累对应资料")
        if kb_reasons:
            # 取 1~2 条最有力的作为整体推荐理由
            for kr in kb_reasons[:1]:
                reasons.append(f"[知识库] {kr}")

        total_score = (industry_score + performance_score + biz_score +
                       visit_score + workload_score + region_score + kb_score)

        scored.append({
            'sales': s,
            'score': round(total_score, 2),
            'details': {
                'industry_match': round(industry_score, 2),
                'performance': round(performance_score, 2),
                'business_advance': round(biz_score, 2),
                'visit_experience': round(visit_score, 2),
                'workload_balance': round(workload_score, 2),
                'region_match': round(region_score, 2),
                'knowledge_match': round(kb_score, 2),
            },
            'reasons': reasons,
        })

    # 按总分降序，相同分时按商机数升序（更空闲优先）
    scored.sort(key=lambda x: (-x['score'], x['sales'].get('biz_count', 0)))
    best = scored[0]

    # 拼接推荐理由：取前3条核心亮点
    top_reasons = best['reasons'][:3]
    reason_text = f'综合评分{best["score"]}分（满分100）。' + '；'.join(top_reasons)

    return {
        'username': best['sales']['username'],
        'name': best['sales']['name'],
        'reason': reason_text,
        'score': best['score'],
        'details': best['details'],
        'all_candidates': [
            {
                'username': item['sales']['username'],
                'name': item['sales']['name'],
                'score': item['score'],
                'details': item['details'],
            } for item in scored[:5]
        ],
    }


def register_routes(app):
    app.register_blueprint(leads_bp)
