"""中国政府采购网采集器。

支持两种模式：
- source.keywords 非空：按业务关键词调用 ccgp 全站搜索接口（bxsearch）逐词抓取，
  结果天然与业务相关，配合关键词过滤层不会清零。
- source.keywords 为空：抓取配置 URL 的公告列表页。
"""
import re
from urllib.parse import urljoin, quote
from collectors import BaseCollector, CollectedItem, register_collector
from routes.leads import _get_search_session, _extract_date_near


class CcgpCollector(BaseCollector):
    """中国政府采购网采集器。"""
    name = 'ccgp_gov'
    label = '中国政府采购网采集器'

    def collect(self):
        keywords = [k.strip() for k in (self.keywords or '').split(',') if k.strip()]
        if keywords:
            return self._collect_by_search(keywords)
        return self._fetch_list(self.url, self.config.get('max_items', 20))

    def _collect_by_search(self, keywords):
        """按业务关键词逐词调用 ccgp 搜索接口，合并去重。"""
        items, seen = [], set()
        per_kw = max(self.config.get('max_items', 20) // min(len(keywords), 4), 5)
        for kw in keywords[:4]:
            url = (
                'http://search.ccgp.gov.cn/bxsearch?searchtype=1&page_index=1'
                '&bidSort=0&pinMu=0&bidType=0&kw=' + quote(kw)
            )
            for it in self._fetch_list(url, per_kw):
                if it.url not in seen:
                    seen.add(it.url)
                    items.append(it)
            if len(items) >= self.config.get('max_items', 20):
                break
        return items

    def _fetch_list(self, list_url, max_items):
        """抓取公告列表页/搜索结果页，提取标题/链接/日期。"""
        if not list_url:
            return []

        session = _get_search_session()
        try:
            resp = session.get(list_url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            })
            if resp.status_code != 200 or not resp.text:
                return []
            resp.encoding = resp.apparent_encoding or 'utf-8'
            html = resp.text
        except Exception as e:
            print(f'[CcgpCollector] 请求失败: {e}')
            return []

        # 正则提取公告链接
        link_pattern = re.compile(r'href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
        procurement_keywords = ['采购', '招标', '中标', '公告', '询价', '谈判', '磋商',
                                '成交', '废标', '更正', '公示', '单一来源']
        items = []
        seen_urls = set()

        for link, raw_title in link_pattern.findall(html):
            title = re.sub(r'<[^>]+>', '', raw_title).strip()
            title = re.sub(r'\s+', ' ', title)
            if not title or len(title) < 8:
                continue
            if not any(k in title for k in procurement_keywords):
                continue
            full_url = urljoin(list_url, link)
            if not full_url or full_url in seen_urls:
                continue
            if any(ext in full_url.lower() for ext in ['.css', '.js', '.jpg', '.png', '.ico']):
                continue
            seen_urls.add(full_url)
            date = _extract_date_near(html, link)
            items.append(CollectedItem(
                url=full_url, title=title, snippet=title,
                publish_date=date, content=''
            ))
            if len(items) >= max_items:
                break

        return items


register_collector('ccgp_gov', CcgpCollector)
