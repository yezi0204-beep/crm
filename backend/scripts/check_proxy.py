"""检查代理设置并测试搜索。"""
import os
import requests
import re

print('HTTP_PROXY:', os.environ.get('HTTP_PROXY', '(not set)'))
print('HTTPS_PROXY:', os.environ.get('HTTPS_PROXY', '(not set)'))
print('http_proxy:', os.environ.get('http_proxy', '(not set)'))
print('https_proxy:', os.environ.get('https_proxy', '(not set)'))

# 测试 DuckDuckGo（不用代理）
try:
    r = requests.get('https://html.duckduckgo.com/html/', params={'q': 'test'},
                     headers={'User-Agent': 'Mozilla/5.0'}, timeout=10,
                     proxies={'http': None, 'https': None})
    print('\nDuckDuckGo (no proxy):', r.status_code, 'len:', len(r.text))
    links = re.findall(r'class="result__a"', r.text)
    print('result__a count:', len(links))
    if r.status_code == 202:
        print('!! Rate limited (202)')
except Exception as e:
    print('DuckDuckGo failed:', e)

# 测试 Bing（不用代理，桌面 UA）
try:
    r2 = requests.get('https://cn.bing.com/search', params={'q': 'test'},
                      headers={'User-Agent': 'Mozilla/5.0'}, timeout=10,
                      proxies={'http': None, 'https': None})
    print('\nBing (no proxy):', r2.status_code, 'len:', len(r2.text))
    # 检查 b_algo
    b_algo = re.findall(r'class="b_algo"', r2.text)
    print('b_algo count:', len(b_algo))
    # 提取所有外部链接
    ext_links = re.findall(r'href="(https?://(?!www\.bing|cn\.bing|m\.bing|go\.microsoft|www\.microsoft|bing\.com)[^"]+)"', r2.text)
    print('external links:', len(ext_links))
    if ext_links:
        for u in ext_links[:3]:
            print('  ', u[:70])
except Exception as e:
    print('Bing failed:', e)
