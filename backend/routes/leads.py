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

线索队列（scraped_leads）：status 流转 pending→evaluated→imported/rejected
AI 评估：复用 ai_agent._evaluate_lead_intent 规则评分；电商/竞品/舆情有专属评分
精准分配：复用 ai_agent._assign_salesperson 选最空闲销售；分配即创建客户

权限模型：线索源管理与抓取仅主任/院长；线索查看全员（按分配/状态/类别筛选）。
"""
import json
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
import requests as http_requests
from flask import request, jsonify

from extensions import get_db, token_required, record_operation_log

from . import leads_bp


# ==================== 线索源 CRUD ====================

@leads_bp.route('/api/leads/sources', methods=['GET'])
@token_required
def list_sources():
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '仅主任/院长可管理线索源', 'data': None})
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        SELECT s.*, (SELECT COUNT(*) FROM scraped_leads sl WHERE sl.source_id = s.id) as lead_count
        FROM lead_sources s ORDER BY s.created_at DESC
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    return jsonify({'code': 200, 'message': 'success', 'data': rows})


@leads_bp.route('/api/leads/sources', methods=['POST'])
@token_required
def create_source():
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '仅主任/院长可管理线索源', 'data': None})
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '请输入线索源名称', 'data': None})
    source_type = data.get('source_type', 'sample')
    if source_type not in ('rss', 'api', 'sample', 'manual', 'html', 'ai_search'):
        return jsonify({'code': 400, 'message': '源类型非法（rss/api/html/ai_search/sample/manual）', 'data': None})
    category = (data.get('category') or '').strip()
    # html/ai_search 源必须指定能力域类别以分发到对应抓取器
    if source_type in ('html', 'ai_search') and not category:
        return jsonify({'code': 400, 'message': '该源类型必须选择能力域类别（招投标监控/电商商机/企业客源/竞品情报/舆情痛点）', 'data': None})
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("""
            INSERT INTO lead_sources (name, source_type, url, config, keywords, industry,
                                      region, enabled, interval_hours, category, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            name, source_type, data.get('url', ''),
            data.get('config', ''), data.get('keywords', ''),
            data.get('industry', ''), data.get('region', ''),
            1 if data.get('enabled', True) else 0,
            int(data.get('interval_hours', 24)),
            category,
        ))
        db.commit()
        record_operation_log(payload['username'], '创建', '线索源', f'创建线索源：{name}({source_type}/{category})')
        return jsonify({'code': 200, 'message': '创建成功', 'data': {'id': cursor.lastrowid}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@leads_bp.route('/api/leads/sources/<int:source_id>', methods=['PUT'])
@token_required
def update_source(source_id):
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    data = request.get_json(silent=True) or {}
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT id FROM lead_sources WHERE id=?", (source_id,))
    if not cursor.fetchone():
        return jsonify({'code': 404, 'message': '线索源不存在', 'data': None})
    try:
        updates, params = [], []
        for f in ['name', 'source_type', 'url', 'config', 'keywords', 'industry', 'region', 'interval_hours', 'category']:
            if f in data:
                updates.append(f"{f}=?")
                params.append(data[f])
        if 'enabled' in data:
            updates.append("enabled=?")
            params.append(1 if data['enabled'] else 0)
        if updates:
            params.append(source_id)
            cursor.execute(f"UPDATE lead_sources SET {', '.join(updates)} WHERE id=?", params)
            db.commit()
            record_operation_log(payload['username'], '编辑', '线索源', f'编辑线索源 ID:{source_id}')
        return jsonify({'code': 200, 'message': '更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@leads_bp.route('/api/leads/sources/<int:source_id>', methods=['DELETE'])
@token_required
def delete_source(source_id):
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cursor = db.cursor()
    try:
        cursor.execute("DELETE FROM scraped_leads WHERE source_id=?", (source_id,))
        cursor.execute("DELETE FROM lead_sources WHERE id=?", (source_id,))
        db.commit()
        record_operation_log(payload['username'], '删除', '线索源', f'删除线索源 ID:{source_id}')
        return jsonify({'code': 200, 'message': '删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 抓取引擎 ====================

@leads_bp.route('/api/leads/sources/<int:source_id>/scrape', methods=['POST'])
@token_required
def scrape_source(source_id):
    """手动触发单个线索源抓取。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM lead_sources WHERE id=?", (source_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '线索源不存在', 'data': None})
    source = dict(row)
    if not source['enabled']:
        return jsonify({'code': 400, 'message': '该线索源已停用', 'data': None})

    leads_data, err = _scrape_source(source)
    inserted = _persist_leads(cursor, leads_data, source_id, source['name'], source.get('category'))
    _mark_scraped(cursor, source_id)
    db.commit()
    record_operation_log(payload['username'], '抓取线索', '智能线索管理',
                         f'抓取源「{source["name"]}」获得 {inserted} 条线索')
    return jsonify({
        'code': 200, 'message': f'抓取完成，新增 {inserted} 条线索',
        'data': {'scraped_count': inserted, 'error': err, 'source_type': source['source_type']}
    })


@leads_bp.route('/api/leads/scrape-all', methods=['POST'])
@token_required
def scrape_all_sources():
    """抓取所有启用的线索源（供定时任务与手动批量调用）。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT * FROM lead_sources WHERE enabled=1")
    sources = [dict(r) for r in cursor.fetchall()]

    total = 0
    details = []
    for source in sources:
        leads_data, err = _scrape_source(source)
        inserted = _persist_leads(cursor, leads_data, source['id'], source['name'], source.get('category'))
        _mark_scraped(cursor, source['id'])
        total += inserted
        details.append({'source': source['name'], 'count': inserted, 'error': err})
    db.commit()
    if total > 0:
        record_operation_log(payload['username'], '批量抓取线索', '智能线索管理',
                             f'批量抓取 {len(sources)} 个源，共 {total} 条线索')
    return jsonify({'code': 200, 'message': f'批量抓取完成，共 {total} 条线索',
                    'data': {'total': total, 'details': details}})


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

# 非商机网站黑名单（百科/地图/导航等通用页面，不应作为线索）
_JUNK_DOMAINS = {
    'baike.baidu.com', 'zhuanlan.zhihu.com', 'baijiahao.baidu.com',
    'map.baidu.com', 'map.bmcx.com', 'earthol.com', '17ditu.com',
    'bajiu.cn', 'earth.google.com', 'ditu.baidu.com',
    'wikipedia.org', 'zh.wikipedia.org',
    'wenku.baidu.com', 'docin.com', 'doc88.com',
}


def _is_junk_url(url):
    """判断 URL 是否为非商机通用页面（百科/地图/文档库等）。"""
    if not url:
        return True
    url_lower = url.lower()
    return any(d in url_lower for d in _JUNK_DOMAINS)


def _build_search_queries(keywords, category, max_queries=3):
    """根据关键词和能力域构建搜索查询列表。

    招投标监控：用 site: 定向搜索真实政企采购网站，确保结果为招标公告而非百科/地图。
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

    # 其他能力域用模板
    template = _CATEGORY_SEARCH_TEMPLATES.get(category, '{kw} {year}')
    if not keywords:
        return [template.format(kw=category or '商机', year=year)]
    return [template.format(kw=kw, year=year) for kw in keywords[:max_queries]]


def _scrape_ai_search(source, config, keywords, category):
    """AI 智能体互联网搜索抓取：搜索 + LLM 结构化提取（LLM 不可用时降级直接提取）。

    工作流程：
    1. 根据 category + keywords 构建搜索查询
    2. _search_web 搜索 DuckDuckGo 获取真实结果
    3. LLM 可用时：调用 LLM 从搜索结果提取结构化商机线索（JSON）
    4. LLM 不可用时：降级为直接提取（标题→商机名，URL→链接，摘要→备注）
    """
    max_items = config.get('max_items', 15)
    max_queries = config.get('max_queries', 3)
    queries = _build_search_queries(keywords, category, max_queries)

    all_results = []
    seen_urls = set()
    for idx, q in enumerate(queries):
        results = _search_web(q, max_results=max_items)
        for r in results:
            if r['url'] not in seen_urls:
                seen_urls.add(r['url'])
                all_results.append(r)
        if len(all_results) >= max_items:
            break
        # 多条查询间加 2 秒延迟，避免搜索引擎限速
        if idx < len(queries) - 1:
            time.sleep(2)

    if not all_results:
        return []  # 搜索无结果，不造假数据

    # 过滤掉百科/地图等非商机通用页面
    filtered_results = [r for r in all_results if not _is_junk_url(r.get('url', ''))]
    if not filtered_results:
        return []  # 全部是通用页面，无商机价值
    all_results = filtered_results

    # 尝试用 LLM 提取结构化线索
    leads = _llm_extract_leads(all_results, keywords, category, max_items)
    if leads is not None:
        # LLM 返回了有效结果（可能是空列表——表示无有价值商机，不再降级保存垃圾数据）
        return leads

    # LLM 调用失败（返回 None）：降级为直接从搜索结果提取线索
    return _fallback_extract_leads(all_results, source, keywords, category, max_items)


def _llm_extract_leads(search_results, keywords, category, max_items):
    """用 LLM 从搜索结果中提取结构化商机线索。LLM 不可用时返回 None。"""
    try:
        from qa_engine import call_llm
    except Exception:
        return None
    # 准备搜索结果摘要（给 LLM 足够上下文提取联系人/地区）
    results_text = '\n'.join(
        '{}. {}\n   链接: {}\n   摘要: {}'.format(i + 1, r['title'][:120], r['url'][:120], r['snippet'][:200])
        for i, r in enumerate(search_results[:max_items])
    )
    kw_str = '、'.join(keywords) if keywords else '不限'
    prompt = (
        '你是一个商机线索分析助手。以下是从互联网搜索到的真实结果，请从中提取有价值的商机线索。\n\n'
        '搜索类别：{cat}\n关注关键词：{kw}\n\n搜索结果：\n{results}\n\n'
        '请提取所有有价值的商机线索，返回 JSON 数组（不要任何其他文字），每个元素包含：\n'
        '- company: 相关公司或机构名（从标题/摘要提取采购方/需求方名称，无则填标题前20字）\n'
        '- opportunity_name: 商机/公告/需求名称（简洁有信息量，去掉网站名等噪声）\n'
        '- link: 真实链接URL（直接取搜索结果的链接，原样复制）\n'
        '- industry: 行业分类（卫星通信/卫星遥感/AI智能体/军工装备/信息技术 之一）\n'
        '- contact_name: 联系人姓名（从摘要中提取项目联系人/采购人姓名，无则留空字符串）\n'
        '- phone: 联系电话（从摘要中提取电话号码，无则留空字符串）\n'
        '- region: 地区（从摘要提取省市，无则填"全国"）\n'
        '- intent: 意向描述（为什么这是商机，一句话说明采购需求和价值）\n'
        '- intent_score: 意向评分0-100整数（明确采购需求且预算大的90+，有采购意向的70-89，潜在需求50-69）\n\n'
        '只返回 JSON 数组，如：[{{"company":"...","opportunity_name":"...","link":"...","industry":"...","contact_name":"...","phone":"...","region":"...","intent":"...","intent_score":80}}]'
    ).format(cat=category or '商机', kw=kw_str, results=results_text)

    messages = [
        {'role': 'system', 'content': '你是商机线索分析助手，只返回JSON数组。'},
        {'role': 'user', 'content': prompt}
    ]
    raw = call_llm(messages)
    if not raw:
        return None
    # 解析 LLM 返回的 JSON（容错：提取 [ ] 之间的内容）
    try:
        # 去除可能的 markdown 代码块包裹
        raw = raw.strip()
        if raw.startswith('```'):
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
        start = raw.find('[')
        end = raw.rfind(']')
        if start >= 0 and end > start:
            raw = raw[start:end + 1]
        items = json.loads(raw)
    except Exception:
        return None

    leads = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        title = (item.get('opportunity_name') or item.get('company') or '').strip()
        if not title:
            continue
        link = (item.get('link') or '').strip()
        # 优先用搜索结果中的真实链接匹配
        for sr in search_results:
            if item.get('link') and item['link'] in sr['url']:
                link = sr['url']
                break
        industry = item.get('industry') or _detect_industry(title)
        contact_name = (item.get('contact_name') or '').strip()
        phone = (item.get('phone') or '').strip()
        region = (item.get('region') or '全国').strip() or '全国'
        leads.append({
            'company': (item.get('company') or title[:30]).strip(),
            'opportunity_name': title,
            'contact_name': contact_name, 'phone': phone, 'email': '',
            'industry': industry,
            'region': region,
            'source': 'AI智能体搜索',
            'link': link,
            'remark': (item.get('intent') or '')[:120],
            'raw_data': json.dumps({
                'title': title, 'link': link, 'industry': industry,
                'intent': item.get('intent', ''), 'intent_score': item.get('intent_score', 50),
                'contact_name': contact_name, 'phone': phone, 'region': region,
                'category': category or '商机', 'source_type': 'ai_search', 'llm_used': True,
                'snippet': next((sr['snippet'] for sr in search_results if sr['url'] == link), '')
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
    all_leads = []
    for r in search_results[:max_items]:
        # 降级路径也过滤百科/地图等非商机页面
        if _is_junk_url(r.get('url', '')):
            continue
        title = r['title']
        text = title + ' ' + r['snippet']
        lead = {
            'company': _extract_company(title) or title[:30],
            'opportunity_name': title,
            'contact_name': '', 'phone': '', 'email': '',
            'industry': _detect_industry(text),
            'region': source.get('region', '全国'),
            'source': 'AI智能体搜索',
            'link': r['url'],
            'remark': r['snippet'][:120] if r['snippet'] else title[:100],
            'raw_data': json.dumps({
                'title': title, 'link': r['url'], 'snippet': r['snippet'][:200],
                'category': category or '', 'source_type': 'ai_search', 'llm_used': False
            }, ensure_ascii=False),
            'category': category or '',
        }
        all_leads.append(lead)
        # 宽松关键词匹配：命中任一拆分后的词即保留
        if not match_terms or any(term in text for term in match_terms):
            leads.append(lead)
    # 若关键词过滤后无结果，返回全部（搜索引擎已按查询筛选，结果有参考价值）
    return leads if leads else all_leads[:max_items]


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
            # HTML 源按 category 分发到对应能力域抓取器
            return _scrape_html_by_category(source, config, keywords, category), None
        if stype == 'ai_search':
            # AI 智能体互联网搜索（无需 URL，用搜索引擎 + LLM 提取）
            return _scrape_ai_search(source, config, keywords, category), None
        if stype == 'sample':
            return _scrape_sample(config.get('count', 5), keywords, industry, region), None
        if stype == 'manual':
            return [], None  # 手动源不自动抓取
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
    """根据文本关键词自动识别行业（覆盖本公司关注领域）。

    用于 RSS 抓取的线索自动分类，使同一采购源中不同领域的商机被归类到
    卫星遥感/卫星通信/AI智能体/军工装备/信息技术。
    """
    if not text:
        return '信息技术'
    # 卫星通信优先匹配（避免被"卫星遥感"的"卫星"误吞）
    if any(k in text for k in ['卫星通信', '通信终端', 'VSAT', '卫星终端', '卫星电话']):
        return '卫星通信'
    if any(k in text for k in ['遥感', '遥感数据', '遥感影像', '遥感监测', '遥感卫星']):
        return '卫星遥感'
    if any(k in text for k in ['智能体', '人工智能', '大模型', 'AI开发', 'AI智能', 'AIGC']):
        return 'AI智能体'
    if any(k in text for k in ['装备', '武器', '军用', '军工', '军采', '国防']):
        return '军工装备'
    return '信息技术'


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
    """线索入库（去重：同源同公司同联系方式视为重复）。返回新增数。

    source_category 由调用方传入（来自 lead_sources.category），用于给线索打能力域标签。
    """
    # 若未传入 category，则从源表查询一次
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
        # 去重检查
        cursor.execute(
            "SELECT id FROM scraped_leads WHERE source_id=? AND company=? AND phone=?",
            (source_id, company, lead.get('phone', ''))
        )
        if cursor.fetchone():
            continue
        # 线索 category 优先取 lead 自带，否则用源 category
        category = lead.get('category') or source_category or ''
        cursor.execute("""
            INSERT INTO scraped_leads (source_id, company, opportunity_name, contact_name, phone, email,
                                        industry, region, source, link, remark, raw_data, category,
                                        status, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
        """, (
            source_id, company, lead.get('opportunity_name', ''),
            lead.get('contact_name', ''), lead.get('phone', ''),
            lead.get('email', ''), lead.get('industry', ''), lead.get('region', ''),
            lead.get('source', source_name), lead.get('link', ''),
            lead.get('remark', ''), lead.get('raw_data', ''), category,
        ))
        inserted += 1
    return inserted


def _mark_scraped(cursor, source_id):
    cursor.execute("UPDATE lead_sources SET last_scraped_at=? WHERE id=?",
                   (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), source_id))


# ==================== 线索队列管理 ====================

@leads_bp.route('/api/leads', methods=['GET'])
@token_required
def list_leads():
    """线索队列列表，支持 status/source_id/keyword/category 筛选。"""
    status = request.args.get('status', '')
    source_id = request.args.get('source_id', '')
    keyword = request.args.get('keyword', '')
    category = request.args.get('category', '')

    db = get_db()
    cursor = db.cursor()
    conditions, params = [], []
    if status:
        conditions.append("sl.status = ?")
        params.append(status)
    if source_id:
        conditions.append("sl.source_id = ?")
        params.append(source_id)
    if category:
        conditions.append("sl.category = ?")
        params.append(category)
    if keyword:
        conditions.append("(sl.company LIKE ? OR sl.remark LIKE ? OR sl.contact_name LIKE ? OR sl.opportunity_name LIKE ?)")
        kw = f'%{keyword}%'
        params.extend([kw, kw, kw, kw])
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
        cursor.execute("""
            UPDATE scraped_leads SET intent_score=?, eval_reason=?, assigned_to=?,
                                     status='evaluated', evaluated_at=?
            WHERE id=?
        """, (score, reason, assignee['username'] if assignee else None,
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
    cursor.execute("""
        UPDATE scraped_leads SET intent_score=?, eval_reason=?, assigned_to=?,
                                 status='evaluated', evaluated_at=?
        WHERE id=?
    """, (score, reason, assignee['username'] if assignee else None,
          datetime.now().strftime('%Y-%m-%d %H:%M:%S'), lead_id))
    db.commit()
    return jsonify({'code': 200, 'message': '评估完成',
                    'data': {'intent_score': score, 'reason': reason,
                             'assigned_to': assignee}})


@leads_bp.route('/api/leads/<int:lead_id>/assign', methods=['POST'])
@token_required
def assign_lead(lead_id):
    """分配线索：创建客户并归属指定销售，线索标记为 imported。

    请求体：assigned_to（可选，默认用 AI 推荐分配）
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
        # 创建客户，归属该销售
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
        cursor.execute("""
            UPDATE scraped_leads SET status='imported', assigned_to=?, evaluated_at=?
            WHERE id=?
        """, (assigned_to, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), lead_id))
        db.commit()
        cursor.execute("SELECT name FROM users WHERE username=?", (assigned_to,))
        sp = cursor.fetchone()
        sp_name = sp['name'] if sp else assigned_to
        record_operation_log(payload['username'], '分配线索', '智能线索管理',
                             f'线索「{lead.get("company")}」分配给 {sp_name}，已创建客户 ID:{new_cust_id}')
        return jsonify({'code': 200, 'message': f'已分配给 {sp_name} 并创建客户',
                        'data': {'customer_id': new_cust_id, 'assigned_to': assigned_to}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@leads_bp.route('/api/leads/<int:lead_id>/reject', methods=['POST'])
@token_required
def reject_lead(lead_id):
    """拒绝/废弃线索。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE scraped_leads SET status='rejected' WHERE id=?", (lead_id,))
    db.commit()
    record_operation_log(payload['username'], '拒绝线索', '智能线索管理', f'拒绝线索 ID:{lead_id}')
    return jsonify({'code': 200, 'message': '已拒绝', 'data': None})


@leads_bp.route('/api/leads/import', methods=['POST'])
@token_required
def import_leads():
    """手动导入线索（JSON 数组），入库后状态为 pending。"""
    payload = request.current_user
    if payload.get('role') not in ('主任', '院长'):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    data = request.get_json(silent=True) or {}
    leads_data = data.get('leads', [])
    if not leads_data:
        return jsonify({'code': 400, 'message': '请提供线索数据', 'data': None})
    db = get_db()
    cursor = db.cursor()
    inserted = _persist_leads(cursor, leads_data, None, '手动导入')
    db.commit()
    record_operation_log(payload['username'], '导入线索', '智能线索管理', f'手动导入 {inserted} 条线索')
    return jsonify({'code': 200, 'message': f'导入 {inserted} 条线索',
                    'data': {'inserted': inserted}})


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
    """加载评估上下文：行业成交统计 + 在职销售工作量。"""
    cursor.execute("""
        SELECT industry, COUNT(*) as cnt FROM business
        WHERE status='active' AND industry IS NOT NULL AND industry!=''
        GROUP BY industry
    """)
    industry_stats = {r['industry']: r['cnt'] for r in cursor.fetchall()}
    cursor.execute("""
        SELECT u.username, u.name, COUNT(b.id) as biz_count
        FROM users u
        LEFT JOIN business b ON b.owner_id = u.username AND b.status='active'
        WHERE u.status='在职' AND u.role='销售'
        GROUP BY u.username ORDER BY biz_count ASC
    """)
    salespeople = [dict(r) for r in cursor.fetchall()]
    return industry_stats, salespeople


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

    # —— AI 智能体搜索线索：优先用 LLM 提供的 intent_score ——
    if raw.get('source_type') == 'ai_search' and raw.get('intent_score') is not None:
        score = max(0, min(100, int(raw.get('intent_score', 50))))
        intent = raw.get('intent', '')
        if intent:
            reasons.append(intent)
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


def _assign_lead(lead, salespeople):
    """选当前商机最少（最空闲）的销售（与 ai_agent._assign_salesperson 一致）。"""
    if not salespeople:
        return None
    return {
        'username': salespeople[0]['username'],
        'name': salespeople[0]['name'],
        'reason': f'当前商机数最少（{salespeople[0]["biz_count"]}单），工作量最均衡',
    }


def register_routes(app):
    app.register_blueprint(leads_bp)
