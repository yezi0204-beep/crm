"""采集器插件基类。

新增网站只需在 collectors/ 下加一个 .py 文件，实现 BaseCollector 接口，
在 collectors/__init__.py 中注册即可。核心业务代码无需修改。

使用 importlib 动态导入，插件注册机制。
"""
import importlib
import os
import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


@dataclass
class CollectedItem:
    """采集器返回的标准化数据结构。"""
    url: str = ''
    title: str = ''
    content: str = ''
    publish_date: str = ''
    snippet: str = ''
    attachment_path: str = ''
    attachment_urls: list = field(default_factory=list)


class BaseCollector(ABC):
    """采集器插件基类。子类必须实现 collect() 方法。

    约定：
    - __init__(source, config) 接收数据源配置
    - collect() 返回 List[CollectedItem]
    - 只采集公开、合法数据，不绕过登录/验证码/访问控制
    """

    name = 'base'
    label = '基类采集器'

    def __init__(self, source: dict, config: dict = None):
        self.source = source
        self.config = config or {}
        self.url = source.get('url', '')
        self.keywords = source.get('keywords', '')

    @abstractmethod
    def collect(self) -> List[CollectedItem]:
        """执行采集，返回标准化数据列表。"""
        pass

    def fetch_detail(self, item: CollectedItem) -> CollectedItem:
        """抓取详情页，填充 content 和 attachment_urls。

        子类可重写以实现特定页面的解析逻辑。
        默认实现：下载 URL 页面，提取正文文本和附件链接。
        """
        if not item.url:
            return item

        session = self._get_session()
        try:
            resp = session.get(item.url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            })
            if resp.status_code != 200 or not resp.text:
                return item
            resp.encoding = resp.apparent_encoding or 'utf-8'
            html = resp.text
        except Exception as e:
            logger.warning(f'[{self.name}] 详情页请求失败 {item.url}: {e}')
            return item

        # 清洗 HTML 提取正文
        try:
            from utils.cleaner import clean_html, clean_title, extract_summary
            content = clean_html(html)
            if content and not item.content:
                item.content = content
            if not item.snippet:
                item.snippet = extract_summary(content, 300)
        except ImportError:
            pass

        # 提取附件链接
        if not item.attachment_urls:
            item.attachment_urls = self._extract_attachment_links(html, item.url)

        return item

    def _get_session(self):
        """获取 requests.Session（复用 leads.py 的 session）。"""
        try:
            from routes.leads import _get_search_session
            return _get_search_session()
        except ImportError:
            import requests
            return requests.Session()

    @staticmethod
    def _extract_attachment_links(html: str, base_url: str) -> list:
        """从 HTML 中提取附件链接（PDF/Word/Excel）。"""
        attachment_exts = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', '.rar')
        links = []
        # 匹配 <a href="...">链接</a>
        pattern = re.compile(r'href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL | re.IGNORECASE)
        for url, text in pattern.findall(html):
            text_clean = re.sub(r'<[^>]+>', '', text).strip()
            url_lower = url.lower()
            if any(url_lower.endswith(ext) for ext in attachment_exts):
                full_url = urljoin(base_url, url)
                if full_url not in links:
                    links.append(full_url)
        return links


# 插件注册表
_registry = {}


def register_collector(name: str, cls):
    """注册采集器插件。"""
    _registry[name] = cls


def get_collector(name: str) -> Optional[type]:
    """获取采集器插件类。"""
    if name not in _registry:
        _load_plugin(name)
    return _registry.get(name)


def list_collectors() -> dict:
    """列出所有已注册采集器。"""
    # 确保所有插件已加载
    _load_all_plugins()
    return {name: cls.label for name, cls in _registry.items()}


def _load_plugin(name: str):
    """动态导入采集器插件。"""
    try:
        importlib.import_module(f'collectors.{name}')
    except ImportError:
        pass


def _load_all_plugins():
    """加载 collectors 目录下所有插件。"""
    collectors_dir = os.path.dirname(__file__)
    for filename in os.listdir(collectors_dir):
        if filename.endswith('.py') and not filename.startswith('_'):
            module_name = filename[:-3]
            try:
                importlib.import_module(f'collectors.{module_name}')
            except Exception as e:
                print(f'[collectors] 加载插件 {module_name} 失败: {e}')
