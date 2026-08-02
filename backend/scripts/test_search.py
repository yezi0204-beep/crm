"""测试搜索引擎可访问性。"""
import requests
import re

# 测试 DuckDuckGo HTML 搜索
try:
    r = requests.get('https://html.duckduckgo.com/html/', params={'q': '卫星遥感 采购 招标'},
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    print('DuckDuckGo:', r.status_code, 'len:', len(r.text))
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"', r.text)
    titles = re.findall(r'class="result__a"[^>]*>([^<]+)</a>', r.text)
    print('结果链接数:', len(links))
    for i, (t, l) in enumerate(zip(titles[:3], links[:3]), 1):
        print('  {}. {} -> {}'.format(i, t.strip()[:50], l[:60]))
except Exception as e:
    print('DuckDuckGo 失败:', e)

print()

# 测试 Bing 搜索
try:
    r2 = requests.get('https://www.bing.com/search', params={'q': '卫星遥感 采购 招标'},
                      headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
    print('Bing:', r2.status_code, 'len:', len(r2.text))
    bing_links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="b_algo"', r2.text)
    print('Bing结果链接数:', len(bing_links))
except Exception as e:
    print('Bing 失败:', e)
