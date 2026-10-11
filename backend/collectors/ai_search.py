"""AI 智能体互联网搜索采集器。

parser_type='ai_search' 的数据源专用：根据 source.category（能力域）+ keywords
构建搜索查询，互联网搜索后由 LLM 提取结构化商机，转为原始情报条目。
复用 routes/leads.py 的搜索与 LLM 提取基建，不重复造轮子。

降级策略：DuckDuckGo/Bing 搜索结果不足时，用 ccgp.gov.cn 搜索接口兜底，
确保在中国大陆网络环境下仍能采集到有效商机。
"""
import re
import time
from urllib.parse import urljoin, quote
from collectors import BaseCollector, CollectedItem, register_collector
from routes.leads import (
    _build_search_queries, _search_web, _is_junk_url,
    _llm_extract_leads, _fallback_extract_leads,
    _get_search_session, _extract_date_near,
)


class AiSearchCollector(BaseCollector):
    """AI 智能体互联网搜索采集器（搜索 → 预过滤 → LLM 提取）。"""
    name = 'ai_search'
    label = 'AI智能体互联网搜索采集器'

    def collect(self):
        category = self.source.get('category') or ''
        max_items = self.config.get('max_items', 15)
        max_queries = self.config.get('max_queries', 3)
        keywords = [k.strip() for k in (self.keywords or '').split(',') if k.strip()]

        # 1. 构建搜索查询并搜索（每个查询取 max_items 条，合并去重）
        queries = _build_search_queries(keywords, category, max_queries)
        all_results, seen = [], set()
        for idx, q in enumerate(queries):
            try:
                results = _search_web(q, max_results=max_items)
            except Exception as e:
                print(f'[AiSearchCollector] 搜索失败: {q} {e}')
                results = []
            for r in results:
                u = r.get('url', '')
                if u and u not in seen:
                    seen.add(u)
                    all_results.append(r)
            if len(all_results) >= max_items * 2:
                break
            if idx < len(queries) - 1:
                time.sleep(2)

        # 2. 预过滤垃圾域名
        all_results = [r for r in all_results if not _is_junk_url(r.get('url', ''))]

        # 2.1 检查搜索结果质量：标题中是否有采购/招标相关词
        procurement_kw = ['采购', '招标', '中标', '公告', '询价', '谈判', '磋商',
                          '成交', '废标', '更正', '公示', '单一来源', '军采', '装备']
        relevant_results = [r for r in all_results
                           if any(k in r.get('title', '') for k in procurement_kw)]

        # 2.2 降级：互联网搜索结果不足或不相关时，用 ccgp.gov.cn 搜索兜底
        if len(relevant_results) < 3:
            ccgp_results = self._search_ccgp(keywords, max_items)
            for r in ccgp_results:
                u = r.get('url', '')
                if u and u not in seen:
                    seen.add(u)
                    all_results.append(r)
            if ccgp_results:
                print(f'[AiSearchCollector] 互联网搜索不相关，ccgp.gov.cn 降级补充 {len(ccgp_results)} 条')

        if not all_results:
            print(f'[AiSearchCollector] 源「{self.source.get("name")}」搜索无有效结果')
            return []

        # 3. LLM 结构化提取（LLM 不可用时降级为关键词提取）
        leads = _llm_extract_leads(all_results, keywords, category, max_items)
        if leads is None:
            leads = _fallback_extract_leads(all_results, self.source, keywords, category, max_items)

        # 4. 转为原始情报条目（content 拼接说明文本，避免过短被垃圾过滤拦截）
        items = []
        for lead in leads or []:
            title = (lead.get('opportunity_name') or lead.get('company') or '').strip()
            link = (lead.get('link') or '').strip()
            if not title or _is_junk_url(link):
                continue
            intent = (lead.get('intent') or '').strip()
            content = (
                f'{title}。{intent}。'
                f'采购单位：{lead.get("company") or "未知"}，'
                f'行业：{lead.get("industry") or "未识别"}，'
                f'地区：{lead.get("region") or "全国"}，'
                f'预算：{lead.get("budget") or "未公布"}，'
                f'采购方式：{lead.get("procurement_method") or "未注明"}，'
                f'发布日期：{lead.get("publish_date") or "未知"}，'
                f'截止日期：{lead.get("deadline") or "未注明"}。'
                f'（来源：AI智能体互联网搜索）'
            )
            items.append(CollectedItem(
                url=link, title=title, content=content,
                snippet=intent[:200] or title,
                publish_date=(lead.get('publish_date') or '').strip(),
            ))
            if len(items) >= max_items:
                break

        # 4.1 LLM 提取结果不足时，直接用搜索结果中含采购关键词的条目
        if len(items) < 3:
            for r in all_results:
                title = r.get('title', '').strip()
                link = r.get('url', '').strip()
                if not title or not link or _is_junk_url(link):
                    continue
                if not any(k in title for k in procurement_kw):
                    continue
                # 避免重复
                if any(it.url == link for it in items):
                    continue
                items.append(CollectedItem(
                    url=link, title=title,
                    content=f'{title}。{r.get("snippet", "")}（来源：ccgp.gov.cn 降级搜索）',
                    snippet=r.get('snippet', '')[:200] or title,
                ))
                if len(items) >= max_items:
                    break

        return items

    def _search_ccgp(self, keywords, max_items=15):
        """ccgp.gov.cn 搜索降级：用政府采购网搜索接口，确保返回真实公告。

        策略：直接访问中国政府采购网首页最新公告列表，而非搜索接口。
        搜索接口返回历史数据，首页返回最新发布的公告。
        """
        if not keywords:
            return []
        session = _get_search_session()
        procurement_keywords = ['采购', '招标', '中标', '公告', '询价', '谈判', '磋商',
                                '成交', '废标', '更正', '公示', '单一来源']
        results = []
        seen_urls = set()

        # 直接访问中国政府采购网首页，获取最新公告（而非搜索历史数据）
        ccgp_urls = [
            'http://www.ccgp.gov.cn/cggg/zygg/gkzb/',   # 中央-公开招标
            'http://www.ccgp.gov.cn/cggg/zygg/zbgg/',   # 中央-中标公告
            'http://www.ccgp.gov.cn/cggg/zygg/fblbgg/', # 中央-废标公告
            'http://www.ccgp.gov.cn/cggg/dfgg/gkzb/',   # 地方-公开招标
            'http://www.ccgp.gov.cn/cggg/dfgg/zbgg/',   # 地方-中标公告
        ]

        for ccgp_url in ccgp_urls:
            if len(results) >= max_items:
                break
            try:
                resp = session.get(ccgp_url, timeout=15, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                    'Accept-Language': 'zh-CN,zh;q=0.9',
                })
                if resp.status_code != 200 or not resp.text:
                    continue
                resp.encoding = resp.apparent_encoding or 'utf-8'
                html = resp.text
            except Exception as e:
                print(f'[AiSearchCollector] ccgp首页访问失败: {ccgp_url} {e}')
                continue

            # 提取公告链接和标题
            link_pattern = re.compile(r'href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
            for link, raw_title in link_pattern.findall(html):
                if len(results) >= max_items:
                    break
                title = re.sub(r'<[^>]+>', '', raw_title).strip()
                title = re.sub(r'\s+', ' ', title)
                if not title or len(title) < 8:
                    continue
                # 只保留含采购关键词的标题
                if not any(k in title for k in procurement_keywords):
                    continue
                # 关键词匹配：标题中至少包含一个业务关键词
                if not any(kw in title for kw in keywords):
                    continue
                full_url = urljoin(ccgp_url, link)
                if not full_url or full_url in seen_urls:
                    continue
                if any(ext in full_url.lower() for ext in ['.css', '.js', '.jpg', '.png', '.ico']):
                    continue
                seen_urls.add(full_url)
                # 从URL提取日期（ccgp URL格式: /202610/t20261009_xxx.htm）
                date_match = re.search(r'/(\d{4})(\d{2})/t(\d{4})(\d{2})(\d{2})_', full_url)
                publish_date = ''
                if date_match:
                    publish_date = f'{date_match.group(3)}-{date_match.group(4)}-{date_match.group(5)}'
                results.append({'title': title, 'url': full_url, 'snippet': title, 'publish_date': publish_date})

        return results

    def fetch_detail(self, item):
        """AI 搜索结果已含 LLM 摘要信息，无需再抓详情页。"""
        return item


register_collector('ai_search', AiSearchCollector)
