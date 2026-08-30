"""数据清洗模块。

功能：
- HTML 标签清洗，提取纯文本正文
- 垃圾内容过滤（广告、导航、页脚等）
- 内容归一化（多余空白、特殊字符）
- 标题清洗
"""
import re

try:
    from lxml import html as lxml_html
    HAS_LXML = True
except ImportError:
    HAS_LXML = False


def clean_html(raw_html: str) -> str:
    """从 HTML 中提取纯文本正文。

    使用 lxml 解析，移除 script/style/nav/footer 等噪声标签，
    保留正文区域的文本内容。
    """
    if not raw_html:
        return ''

    if not HAS_LXML:
        # 降级：正则去除标签
        text = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        return _normalize_whitespace(text)

    try:
        doc = lxml_html.fromstring(raw_html)
    except Exception:
        return _normalize_whitespace(re.sub(r'<[^>]+>', ' ', raw_html))

    # 移除噪声标签
    for tag in ('script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'noscript'):
        for el in doc.xpath(f'//{tag}'):
            el.getparent().remove(el)

    # 提取正文文本
    text = doc.text_content()
    return _normalize_whitespace(text)


def _normalize_whitespace(text: str) -> str:
    """归一化空白字符：多余空格/换行/制表符。"""
    if not text:
        return ''
    # 统一换行
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # 制表符转空格
    text = text.replace('\t', ' ')
    # 连续空格压缩
    text = re.sub(r'[ ]{2,}', ' ', text)
    # 连续空行压缩
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_title(raw_title: str) -> str:
    """清洗标题：移除 HTML 标签、多余空白、网站后缀。"""
    if not raw_title:
        return ''
    title = re.sub(r'<[^>]+>', '', raw_title).strip()
    title = re.sub(r'\s+', ' ', title)
    # 移除常见网站后缀
    title = re.sub(r'\s*[-_|]\s*(中国政府采购网|政府采购|ccgp\.gov\.cn).*$', '', title, flags=re.IGNORECASE)
    return title.strip()


# 垃圾内容特征（正文太短或包含太多导航文字）
_JUNK_CONTENT_PATTERNS = [
    r'^(首页|网站地图|联系我们|友情链接|版权所有)',
    r'^(登录|注册|忘记密码|记住我)',
]

# 最小正文长度（字符数）
MIN_CONTENT_LENGTH = 50


def is_junk_content(content: str, title: str = '') -> bool:
    """判断内容是否为垃圾/无效内容。

    规则：
    - 正文过短（< 50 字符）
    - 标题和正文都是导航类文字
    - 纯数字/符号
    """
    if not content:
        return True

    content = content.strip()
    if len(content) < MIN_CONTENT_LENGTH:
        return True

    # 检查是否全是导航文字
    for pattern in _JUNK_CONTENT_PATTERNS:
        if re.match(pattern, content):
            return True

    # 数字/符号占比过高
    alpha_count = sum(1 for c in content if c.isalpha() or '\u4e00' <= c <= '\u9fff')
    if alpha_count < len(content) * 0.2:
        return True

    return False


def extract_summary(content: str, max_length: int = 200) -> str:
    """从正文提取摘要（取前 N 个有效字符）。"""
    if not content:
        return ''
    summary = content.strip()
    if len(summary) > max_length:
        summary = summary[:max_length] + '...'
    return summary


def extract_contact_info(content: str) -> dict:
    """从正文中提取联系方式（电话、邮箱、地址）。"""
    info = {'phones': [], 'emails': [], 'addresses': []}

    if not content:
        return info

    # 电话：座机或手机
    phone_pattern = re.compile(
        r'(?:1[3-9]\d{9}'  # 手机
        r'|0\d{2,3}[-\s]?\d{7,8}'  # 座机
        r'|400[-\s]?\d{3}[-\s]?\d{4})'  # 400
    )
    info['phones'] = list(set(phone_pattern.findall(content)))

    # 邮箱
    email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    info['emails'] = list(set(email_pattern.findall(content)))

    return info
