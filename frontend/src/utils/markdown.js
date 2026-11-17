/**
 * 轻量 Markdown 渲染器（无第三方依赖，输出已转义的安全 HTML）。
 * 支持：标题、无序/有序列表、表格、代码块、行内代码、加粗、斜体、链接、分隔线。
 * 用于智能助手回答的富文本展示（仿 DeepSeek 的 Markdown 输出）。
 */

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// 行内样式：加粗、斜体、行内代码、链接
function renderInline(text) {
  let s = escapeHtml(text)
  s = s.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>')
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>')
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>')
  return s
}

function splitTableRow(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim())
}

export function renderMarkdown(raw) {
  if (!raw) return ''
  const lines = String(raw).replace(/\r\n/g, '\n').split('\n')
  const out = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // 代码块
    if (/^```/.test(line.trim())) {
      const lang = line.trim().replace(/^```/, '').trim()
      const buf = []
      i++
      while (i < lines.length && !/^```/.test(lines[i].trim())) {
        buf.push(lines[i])
        i++
      }
      i++
      const code = escapeHtml(buf.join('\n'))
      out.push(`<pre class="md-pre"><code${lang ? ` data-lang="${escapeHtml(lang)}"` : ''}>${code}</code></pre>`)
      continue
    }

    // 表格：表头 + 分隔行（|---|）
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const head = splitTableRow(line)
      i += 2
      const rows = []
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        rows.push(splitTableRow(lines[i]))
        i++
      }
      out.push(
        '<table class="md-table"><thead><tr>' +
        head.map(c => `<th>${renderInline(c)}</th>`).join('') +
        '</tr></thead><tbody>' +
        rows.map(r => '<tr>' + r.map(c => `<td>${renderInline(c)}</td>`).join('') + '</tr>').join('') +
        '</tbody></table>'
      )
      continue
    }

    // 分隔线
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      out.push('<hr class="md-hr" />')
      i++
      continue
    }

    // 标题
    const h = line.match(/^\s*(#{1,6})\s+(.*)$/)
    if (h) {
      const level = Math.min(h[1].length + 1, 6)
      out.push(`<h${level} class="md-h${level}">${renderInline(h[2])}</h${level}>`)
      i++
      continue
    }

    // 无序列表
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ''))
        i++
      }
      out.push('<ul class="md-ul">' + items.map(t => `<li>${renderInline(t)}</li>`).join('') + '</ul>')
      continue
    }

    // 有序列表
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = []
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ''))
        i++
      }
      out.push('<ol class="md-ol">' + items.map(t => `<li>${renderInline(t)}</li>`).join('') + '</ol>')
      continue
    }

    // 空行
    if (!line.trim()) {
      i++
      continue
    }

    // 普通段落：合并连续非空行
    const buf = [line]
    i++
    while (i < lines.length && lines[i].trim() &&
      !/^\s*(#{1,6}\s|[-*+]\s|\d+\.\s|```|\|)/.test(lines[i]) &&
      !/^\s*(-{3,}|\*{3,})\s*$/.test(lines[i])) {
      buf.push(lines[i])
      i++
    }
    out.push(`<p class="md-p">${buf.map(renderInline).join('<br/>')}</p>`)
  }

  return out.join('')
}
