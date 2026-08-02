"""调试搜索引擎响应。"""
import requests
import re

q = '卫星遥感 采购 招标 2026'
ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# DuckDuckGo
print('=== DuckDuckGo ===')
try:
    r = requests.get('https://html.duckduckgo.com/html/', params={'q': q}, headers={'User-Agent': ua}, timeout=12)
    print('status:', r.status_code, 'len:', len(r.text))
    # 检查是否被限速
    if 'anomaly' in r.text.lower() or 'rate' in r.text.lower():
        print('!! 检测到限速/异常页面')
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"', r.text)
    print('result__a 链接数:', len(links))
    # 看前500字符了解结构
    if not links:
        print('HTML片段:', r.text[:500])
except Exception as e:
    print('失败:', e)

print()

# Bing
print('=== Bing ===')
try:
    r2 = requests.get('https://www.bing.com/search', params={'q': q}, headers={'User-Agent': ua}, timeout=12)
    print('status:', r2.status_code, 'len:', len(r2.text))
    b_algo = re.findall(r'class="b_algo"', r2.text)
    print('b_algo 出现次数:', len(b_algo))
    # 尝试其他 Bing 结构
    h2_links = re.findall(r'<h2><a[^>]+href="(https?://[^"]+)"', r2.text)
    print('h2>a 链接数:', len(h2_links))
    if not b_algo and not h2_links:
        # 看是否有其他结果容器
        print('HTML片段(搜索结果区域):', r2.text[2000:3000] if len(r2.text) > 3000 else r2.text[:1000])
except Exception as e:
    print('失败:', e)
