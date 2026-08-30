"""AI 智能体互联网搜索采集器。

parser_type='ai_search' 的数据源专用：根据 source.category（能力域）+ keywords
构建搜索查询，互联网搜索后由 LLM 提取结构化商机，转为原始情报条目。
复用 routes/leads.py 的搜索与 LLM 提取基建，不重复造轮子。
"""
import time
from collectors import BaseCollector, CollectedItem, register_collector
from routes.leads import (
    _build_search_queries, _search_web, _is_junk_url,
    _llm_extract_leads, _fallback_extract_leads,
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
        return items

    def fetch_detail(self, item):
        """AI 搜索结果已含 LLM 摘要信息，无需再抓详情页。"""
        return item


register_collector('ai_search', AiSearchCollector)
