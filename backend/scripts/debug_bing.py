"""调试 Bing HTML 中的链接结构。"""
import requests
import re

q = '卫星遥感 采购 招标 2026'
ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

r = requests.get('https://www.bing.com/search', params={'q': q}, headers={'User-Agent': ua}, timeout=12)
html = r.text

# 尝试多种 Bing 结果选择器
patterns = [
    ('b_algo', r'class="b_algo"'),
    ('b_caption', r'class="b_caption"'),
    ('b_title', r'class="b_title"'),
    ('tilk', r'class="tilk"'),
    ('b_results', r'id="b_results"'),
    ('all http links', r'https?://[^\s"\'<>]{20,}'),
    ('cite tags', r'<cite[^>]*>([^<]+)</cite>'),
]
for name, pat in patterns:
    matches = re.findall(pat, html)
    print('{}: {} matches'.format(name, len(matches)))

# 看看 b_results 区域内容
m = re.search(r'id="b_results"(.*?)(?:id="b_context"|</body>)', html, re.DOTALL)
if m:
    content = m.group(1)
    print('\nb_results区域长度:', len(content))
    # 提取区域内所有链接
    links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]{4,})</a>', content)
    print('b_results内链接数:', len(links))
    for url, title in links[:5]:
        title_clean = re.sub(r'<[^>]+>', '', title).strip()
        print('  - {} -> {}'.format(title_clean[:50], url[:60]))

# DuckDuckGo lite
print('\n=== DuckDuckGo Lite ===')
try:
    r2 = requests.get('https://lite.duckduckgo.com/lite/', params={'q': q}, headers={'User-Agent': ua}, timeout=12)
    print('status:', r2.status_code, 'len:', len(r2.text))
    # lite 版结果链接
    lite_links = re.findall(r'class="result-link"[^>]*>(.*?)</a>', r2.text, re.DOTALL)
    print('result-link数:', len(lite_links))
    lite_urls = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*rel="nofollow"', r2.text)
    print('nofollow链接数:', len(lite_urls))
    # 看结构
    a_links = re.findall(r'<a[^>]+href="(https?://[^"]+)"', r2.text)
    print('所有http链接数:', len(a_links))
    if a_links:
        for u in a_links[:5]:
            print('  ', u[:70])
except Exception as e:
    print('失败:', e)
