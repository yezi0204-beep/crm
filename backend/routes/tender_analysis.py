"""招标文件研判模块（竞争性磋商文件线上分析）。

流程：
  上传招标/磋商文件（pdf/docx/xls）→ 自动解析全文
  → 手动点击"AI研判" → 章节抽取 + 我方能力清单注入 → LLM 综合分析
  → 输出结构化研判报告（项目概况/资格要求/能力匹配/评分要点/风险点/投标建议）
"""
import json
import os
import re
import logging
from datetime import datetime

from flask import request, jsonify

from extensions import get_db, token_required, record_operation_log, user_can
from . import tender_bp
from utils.attachment_parser import parse_attachment

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads', 'tender')
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'xls', 'xlsx', 'txt'}
MAX_TEXT_LEN = 12000  # 送入 LLM 的正文上限（超出则做章节抽取）


def register_routes(app):
    app.register_blueprint(tender_bp, url_prefix='/api/tender-analysis')


def _ensure_tables():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS tender_docs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            filepath VARCHAR(500) NOT NULL,
            filesize BIGINT DEFAULT 0,
            text_len INT DEFAULT 0,
            extracted_text LONGTEXT,
            analysis_result LONGTEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'uploaded',
            error_msg VARCHAR(500),
            created_by VARCHAR(191),
            created_by_name VARCHAR(191),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            analyzed_at DATETIME DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS tender_feedbacks (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            doc_id BIGINT NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_by VARCHAR(191),
            created_by_name VARCHAR(191),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_doc (doc_id)
        )
    """)


def _now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ==================== 上传与文件管理 ====================

@tender_bp.route('/upload', methods=['POST'])
@token_required
def upload_tender():
    _ensure_tables()
    payload = request.current_user
    username = payload['username']

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'code': 400, 'message': '请选择文件', 'data': None})

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'code': 400, 'message': f'仅支持 {"/".join(sorted(ALLOWED_EXTENSIONS))} 格式', 'data': None})

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    # 防重名：时间戳前缀 + 文件名非法字符清洗
    clean_name = re.sub(r'[\\/:*?"<>|]', '_', filename)
    safe_name = "{}_{}".format(datetime.now().strftime('%Y%m%d%H%M%S'), clean_name)
    filepath = os.path.join(UPLOAD_DIR, safe_name)
    file.save(filepath)

    filesize = os.path.getsize(filepath)
    text = parse_attachment(filepath)
    if not text:
        status = 'parse_failed'
        error_msg = '未能从文件中提取到文本（可能是扫描件PDF，请提供文字版）'
        os.remove(filepath) if os.path.exists(filepath) else None
        return jsonify({'code': 400, 'message': error_msg, 'data': None})

    db = get_db()
    db.execute("""
        INSERT INTO tender_docs (filename, filepath, filesize, text_len, extracted_text,
                                 status, created_by, created_by_name, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (filename, filepath, filesize, len(text), text,
          'uploaded', username, payload.get('name'), _now_str()))
    db.commit()
    row = db.execute("SELECT id FROM tender_docs WHERE filepath=?", (filepath,)).fetchone()

    record_operation_log(username, '上传', '招标文件', filename)
    return jsonify({'code': 200, 'message': '上传成功，可点击"AI研判"开始分析',
                    'data': {'id': row['id'] if row else None}})


@tender_bp.route('', methods=['GET'])
@token_required
def list_tenders():
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    db = get_db()

    if user_can(username, 'data.view_all'):
        rows = db.execute("""
            SELECT id, filename, filesize, text_len, status, error_msg,
                   created_by_name, created_at, analyzed_at,
                   LEFT(analysis_result, 4) AS has_result
            FROM tender_docs ORDER BY id DESC
        """).fetchall()
    else:
        rows = db.execute("""
            SELECT id, filename, filesize, text_len, status, error_msg,
                   created_by_name, created_at, analyzed_at,
                   LEFT(analysis_result, 4) AS has_result
            FROM tender_docs WHERE created_by=? ORDER BY id DESC
        """, (username,)).fetchall()
    return jsonify({'code': 200, 'message': 'success', 'data': [dict(r) for r in rows]})


@tender_bp.route('/<int:tid>', methods=['GET'])
@token_required
def get_tender(tid):
    _ensure_tables()
    row = get_db().execute(
        "SELECT * FROM tender_docs WHERE id=?", (tid,)
    ).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '文件不存在', 'data': None})
    data = dict(row)
    # 列表/详情均不返回全文（太大），详情返回前800字预览
    preview = (data.get('extracted_text') or '')[:800]
    analysis = None
    if data.get('analysis_result'):
        try:
            analysis = json.loads(data['analysis_result'])
        except (ValueError, TypeError):
            analysis = None
    data['text_preview'] = preview
    data.pop('extracted_text', None)
    data['analysis'] = analysis
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@tender_bp.route('/<int:tid>', methods=['DELETE'])
@token_required
def delete_tender(tid):
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    db = get_db()
    row = db.execute("SELECT * FROM tender_docs WHERE id=?", (tid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '文件不存在', 'data': None})
    if row['created_by'] != username and not user_can(username, 'data.view_all'):
        return jsonify({'code': 403, 'message': '仅上传人或管理员可删除', 'data': None})

    try:
        if row['filepath'] and os.path.exists(row['filepath']):
            os.remove(row['filepath'])
    except OSError as e:
        logger.warning(f'删除文件失败 {row["filepath"]}: {e}')

    db.execute("DELETE FROM tender_feedbacks WHERE doc_id=?", (tid,))
    db.execute("DELETE FROM tender_docs WHERE id=?", (tid,))
    db.commit()
    record_operation_log(username, '删除', '招标文件', row['filename'])
    return jsonify({'code': 200, 'message': '已删除', 'data': None})


# ==================== AI 研判 ====================

# 竞争性磋商文件关键章节标题模式（用于超长文件的关键章节抽取）
_SECTION_PATTERNS = [
    (r'(磋商邀请|采购公告|项目概况)', 2),
    (r'(供应商资格|资格要求|供应商须知)', 3),
    (r'(采购需求|技术要求|服务要求|项目需求)', 4),
    (r'(评审办法|评分标准|磋商程序|响应文件评审)', 4),
    (r'(商务要求|合同条款|付款方式|付款条款)', 3),
    (r'(磋商保证金|响应截止|磋商时间|开启时间)', 2),
    (r'(响应文件格式|投标文件格式|格式要求)', 1),
]


def _extract_key_sections(text):
    """超长文件按章节标题抽取关键内容，压缩到 MAX_TEXT_LEN 左右。"""
    lines = text.split('\n')
    # 按疑似章节标题切分
    sections = []  # [(title, content)]
    cur_title, cur_lines = '（文件开头）', []
    for line in lines:
        stripped = line.strip()
        is_heading = (
            1 < len(stripped) < 40
            and (re.match(r'^(第[一二三四五六七八九十百\d]+[章节部分]|[一二三四五六七八九十]+、|\d+(\.\d+)+\s|\d+、)', stripped)
                 or re.match(r'^(磋商邀请|采购公告|供应商须知|采购需求|评审办法|评分标准|商务要求|合同条款|响应文件格式)', stripped))
        )
        if is_heading:
            if cur_lines:
                sections.append((cur_title, '\n'.join(cur_lines)))
            cur_title, cur_lines = stripped, []
        else:
            cur_lines.append(line)
    if cur_lines:
        sections.append((cur_title, '\n'.join(cur_lines)))

    # 按关键章节优先级挑选
    picked = []
    budget = MAX_TEXT_LEN
    # 先按 _SECTION_PATTERNS 匹配优先级
    prioritized = []
    for title, content in sections:
        weight = 0
        for pat, w in _SECTION_PATTERNS:
            if re.search(pat, title):
                weight = max(weight, w)
                break
        prioritized.append((weight, title, content))
    prioritized.sort(key=lambda x: -x[0])

    for weight, title, content in prioritized:
        if budget <= 0:
            break
        take = content[:min(len(content), 3500)]
        if weight > 0 or len(picked) == 0:
            picked.append(f'【{title}】\n{take}')
            budget -= len(take)
    return '\n\n'.join(picked)


def _load_capability_context(db, text):
    """加载我方能力清单 + 规则匹配命中项。返回 (caps_hint, matched_hint, meta)。"""
    caps_hint = ''
    matched_hint = ''
    meta = {'capability_count': 0, 'matched_capabilities': []}
    try:
        from capability_matcher import load_capabilities, match_project_capabilities
        caps = load_capabilities(db)
        if caps:
            meta['capability_count'] = len(caps)
            lines = []
            for c in caps:
                level = c.get('capability_level') or c.get('level') or 'normal'
                level_text = {'mature': '成熟', 'growing': '成长中',
                              'learning': '学习中', 'normal': '一般'}.get(level, level)
                parts = [f"{c['name']}（{level_text}）"]
                if c.get('capability_desc') or c.get('description'):
                    parts.append((c.get('capability_desc') or c.get('description') or '')[:60])
                if c.get('products'):
                    parts.append(f"产品：{'、'.join(c['products'][:5])}")
                if c.get('solutions'):
                    parts.append(f"方案：{'、'.join(c['solutions'][:3])}")
                lines.append('- ' + '；'.join(parts))
            caps_hint = '【我方能力清单（来自CRM业务标签）】\n' + '\n'.join(lines)
            cap_result = match_project_capabilities(text[:3000], '', db)
            matched = cap_result.get('matched', [])
            if matched:
                meta['matched_capabilities'] = [m['name'] for m in matched[:8]]
                matched_hint = '\n\n【关键词规则已命中的我方能力（重点参考）】\n' + '\n'.join(
                    f"- {m['name']}（置信度{m['confidence']}%）" for m in matched[:8]
                )
    except Exception as e:
        logger.warning(f'加载能力清单失败: {e}')
    if not caps_hint:
        caps_hint = '【我方能力清单】（暂未配置，请按通用研究院能力谨慎评估）'
    return caps_hint, matched_hint, meta


def _load_qualification_context(db):
    """加载我方企业资质与人员资质清单。返回 (quals_hint, meta)。"""
    quals_hint = ''
    meta = {'company_qual_count': 0, 'personnel_qual_count': 0}
    try:
        company = db.execute("""
            SELECT qualification_type, qualification_name, level, scope
            FROM company_qualifications WHERE status='有效'
            ORDER BY id
        """).fetchall()
        personnel = db.execute("""
            SELECT p.name, p.qualification_name, p.level, p.specialty
            FROM personnel_qualifications p
            WHERE p.status='有效'
            ORDER BY p.id
        """).fetchall()
        meta['company_qual_count'] = len(company)
        meta['personnel_qual_count'] = len(personnel)

        lines = []
        if company:
            lines.append('【我方企业资质清单（均为有效证书）】')
            for r in company:
                parts = [f"{r['qualification_name'] or r['qualification_type']}"]
                if r.get('level'):
                    parts.append(f"等级:{r['level']}")
                if r.get('scope'):
                    parts.append(f"范围:{r['scope'][:60]}")
                lines.append('- ' + '；'.join(parts))
        if personnel:
            lines.append('【我方人员资质清单（均为有效）】')
            for r in personnel:
                parts = [f"{r['name']}：{r['qualification_name']}"]
                if r.get('level'):
                    parts.append(f"{r['level']}")
                if r.get('specialty'):
                    parts.append(f"专业:{r['specialty'][:30]}")
                lines.append('- ' + '；'.join(parts))
        if lines:
            quals_hint = '\n'.join(lines)
        else:
            quals_hint = '【我方资质清单】（资质管理模块暂无有效记录）'
    except Exception as e:
        logger.warning(f'加载资质清单失败: {e}')
        quals_hint = '【我方资质清单】（加载失败）'
    return quals_hint, meta


def _load_knowledge_context(text):
    """从知识库检索相关片段。返回 (kb_hint, meta)。"""
    meta = {'kb_hits': []}
    try:
        from vector_search import semantic_search
        query = (text or '')[:1000].replace('\n', ' ')
        if len(query.strip()) < 30:
            return '', meta
        hits = semantic_search(query, top_k=6)
        lines, seen = [], set()
        for h in hits:
            if h['doc_id'] in seen:
                continue
            seen.add(h['doc_id'])
            snippet = (h.get('chunk_text') or h.get('summary') or '').strip()
            if not snippet:
                continue
            lines.append(f"- 【{h['title']}】{snippet[:250]}")
            meta['kb_hits'].append(h['title'])
            if len(lines) >= 5:
                break
        if not lines:
            return '', meta
        return '【知识库相关参考（历史交流纪要/行业资料）】\n' + '\n'.join(lines), meta
    except Exception as e:
        logger.warning(f'知识库检索失败: {e}')
        return '', meta


@tender_bp.route('/<int:tid>/analyze', methods=['POST'])
@token_required
def analyze_tender(tid):
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    db = get_db()
    row = db.execute("SELECT * FROM tender_docs WHERE id=?", (tid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '文件不存在', 'data': None})
    if row['status'] == 'analyzing':
        return jsonify({'code': 400, 'message': '正在分析中，请稍候', 'data': None})

    text = row['extracted_text'] or ''
    if len(text) < 50:
        return jsonify({'code': 400, 'message': '文件文本内容过少，无法分析', 'data': None})

    db.execute("UPDATE tender_docs SET status='analyzing', error_msg=NULL WHERE id=?", (tid,))
    db.commit()

    try:
        body = text if len(text) <= MAX_TEXT_LEN else _extract_key_sections(text)
        caps_hint, matched_hint, cap_meta = _load_capability_context(db, text)
        quals_hint, qual_meta = _load_qualification_context(db)
        kb_hint, kb_meta = _load_knowledge_context(text)
        sources = {
            'text_mode': '全文' if len(text) <= MAX_TEXT_LEN else f'关键章节抽取（原文{len(text)}字）',
            'company_qual_count': qual_meta['company_qual_count'],
            'personnel_qual_count': qual_meta['personnel_qual_count'],
            'capability_count': cap_meta['capability_count'],
            'matched_capabilities': cap_meta['matched_capabilities'],
            'kb_hits': kb_meta['kb_hits'],
            'feedback_rounds': db.execute("SELECT COUNT(*) c FROM tender_feedbacks WHERE doc_id=? AND role='user'", (tid,)).fetchone()['c'],
        }

        prompt = f"""以下是研究院拟参与投标/磋商的采购文件内容，以及我方资质清单、能力清单和知识库参考资料。请以资深投标评审专家视角，为研究院管理层做投标决策研判。

{quals_hint}

{caps_hint}{matched_hint}
{kb_hint}

【采购文件内容（{'全文' if len(text) <= MAX_TEXT_LEN else '关键章节节选'}，共{len(text)}字）】
{body}

请综合分析并只返回如下 JSON（不要输出其他内容）：
{{
  "project_overview": {{
    "project_name": "项目名称",
    "purchaser": "采购人/采购单位",
    "budget": "预算金额（原文有则填，无则空）",
    "procurement_method": "采购方式（竞争性磋商/公开招标等）",
    "response_deadline": "响应文件递交截止时间",
    "service_period": "服务期/工期",
    "location": "项目地点"
  }},
  "qualification_requirements": ["供应商资格要求逐条列出，含资质证书、业绩、人员、财务等硬性门槛"],
  "qualification_check": "对照上方【我方企业资质清单】【我方人员资质清单】逐条判断：清单中能对应上的必须明确写'符合'并引用具体证书名称/等级或人员姓名及职称（如'符合——我方持有乙级测绘资质（摄影测量与遥感专业）'）；清单确实没有的才写'不确定'或'可能不符合'并说明缺什么。禁止在有对应证书的情况下仍写'需核查'",
  "capability_match": {{
    "matched": ["我方能覆盖的需求点及对应能力"],
    "missing": ["我方明显缺失或存疑的能力"],
    "summary": "能力匹配综合结论（一段话）"
  }},
  "scoring_highlights": [
    {{"item": "评分项", "weight": "分值/权重", "strategy": "得分策略建议"}}
  ],
  "scoring_detail": [
    {{"category": "评分大类（如技术方案/商务/价格/人员配置）",
      "max_score": 0,
      "sub_items": [
        {{"name": "子项名称", "max_score": 0, "criteria": "评分细则/得分要点（引用原文标准）"}}
      ]
    }}
  ],
  "scoring_analysis": {{
    "score_items": [
      {{"item": "评分项名称", "max_score": 0, "est_score": 0, "confidence": "high|medium|low", "basis": "得分依据（引用招标文件评分标准+我方能力/资质/业绩对应点）"}}
    ],
    "loss_items": [
      {{"item": "失分项名称", "est_loss": 0, "reason": "失分原因（能力不足/缺少类似业绩/参数偏差等）", "mitigation": "减损措施"}}
    ],
    "total_max_score": 0,
    "est_total_score": 0,
    "summary": "得分预估汇总（一段话，说明得分主要来源和主要失分点）"
  }},
  "recommended_price": {{
    "price": 0,
    "price_range_low": 0,
    "price_range_high": 0,
    "basis": "报价依据（预算金额、成本测算、竞争对手分析、价格分计算规则等）",
    "strategy": "报价策略（如略低于预算上限/基准价下浮比例/最优报价区间推算逻辑）",
    "price_score_est": 0,
    "price_score_max": 0
  }},
  "key_requirements": {{
    "technical": ["关键技术要求/参数门槛，逐条列出"],
    "commercial": ["商务要求：付款方式、履约保证金、服务期、违约条款等"]
  }},
  "risks": [
    {{"category": "废标风险|资质风险|商务风险|技术风险|履约风险|价格风险|其他",
      "severity": "high|medium|low",
      "description": "风险描述（尽量引用原文关键条款）",
      "suggestion": "应对建议"}}
  ],
  "conclusion": {{
    "recommendation": "建议投标|谨慎投标|不建议投标",
    "feasibility_score": 0,
    "reason": "综合研判理由（一段话，点明最关键的2-3个因素）"
  }}
}}

研判要求：
1. 资格要求逐条对照【我方企业资质清单】【我方人员资质清单】判断，命中证书必须引用具体证书名称/等级/人员姓名作为依据；有硬性资质门槛达不到的必须列为 high 风险；
2. 风险点务必具体（引用原文条款/数字），不要泛泛而谈；至少给出3条，最多8条；
3. 评分标准若有分值表，给出高分策略；
3.1 scoring_detail 完整列出招标文件评分表：按大类拆分，每个大类下 sub_items 逐条列出子项名称/满分/评分细则（引用原文标准），不得遗漏任何评分项；
3.2 scoring_analysis 逐项估算得分：score_items 按招标文件评分项拆分，est_score 不得超 max_score；loss_items 列出预计失分项及减损措施；total_max_score 和 est_total_score 必须与各项分值合计一致；
3.3 recommended_price 必须给出：price（建议报价金额，单位元）、price_range_low/high（合理报价区间）、basis（报价依据：预算金额、成本测算、价格分计算规则）、strategy（报价策略）、price_score_est/max（预估价格分）；若招标文件未公布预算，结合项目规模和行业行情推算；
4. feasibility_score 为0-100整数，反映综合可行性；
5. 若文件信息不足以判断某项，写"不确定"，不要编造；
6. 知识库片段仅作辅助参考：可据此判断我方与采购人是否有历史交流/合作基础（如采购人曾与我方交流过、有类似项目往来），相关背景写入 conclusion.reason 或风险的 suggestion；无直接关联时忽略，不要强行关联；
7. 所有关键判断必须可追溯依据：引用招标文件内容的标注（依据：招标文件原文"…"）；引用我方资质的标注（依据：资质管理-证书名）；引用能力的标注（依据：业务标签-标签名）；引用知识库的标注（依据：知识库-《文档标题》）；AI推断的标注（依据：综合推断）。标注融入basis/description/reason等文本字段末尾，不新增字段。"""

        from qa_engine import call_llm
        resp = call_llm(
            [{'role': 'system', 'content': '你是资深投标评审专家，熟悉政府采购竞争性磋商流程，为研究院提供投标决策研判。判断资格符合性时，必须以用户消息中提供的企业资质清单和人员资质清单为准逐条对照，不得凭空说"需核查"。只返回JSON，不要输出其他内容。'},
             {'role': 'user', 'content': prompt}],
            max_tokens=8192,
            timeout=300,
        )
        if not resp:
            raise RuntimeError('LLM 服务不可用')

        content = resp['choices'][0]['message']['content'] if isinstance(resp, dict) and resp.get('choices') else str(resp)
        result = _parse_llm_json(content)
        if not result or 'project_overview' not in result:
            raise RuntimeError('AI 返回格式异常，请重试')

        result['_sources'] = sources
        db.execute("""
            UPDATE tender_docs SET status='analyzed', analysis_result=?, analyzed_at=?
            WHERE id=?
        """, (json.dumps(result, ensure_ascii=False), _now_str(), tid))
        db.commit()
        record_operation_log(username, 'AI研判', '招标文件', row['filename'])
        return jsonify({'code': 200, 'message': '研判完成', 'data': result})
    except Exception as e:
        logger.exception(f'招标文件研判失败 id={tid}: {e}')
        db.execute("UPDATE tender_docs SET status='failed', error_msg=? WHERE id=?",
                   (str(e)[:480], tid))
        db.commit()
        return jsonify({'code': 500, 'message': f'研判失败：{e}', 'data': None})


def _parse_llm_json(content):
    """从 LLM 输出中提取 JSON（容忍 ```json 包裹）。"""
    if not content:
        return None
    content = content.strip()
    m = re.search(r'```(?:json)?\s*(\{.*\})\s*```', content, re.S)
    if m:
        content = m.group(1)
    try:
        return json.loads(content)
    except (ValueError, TypeError):
        pass
    # 宽松截取首尾大括号
    start, end = content.find('{'), content.rfind('}')
    if 0 <= start < end:
        try:
            return json.loads(content[start:end + 1])
        except (ValueError, TypeError):
            return None
    return None


# ==================== 对话式反馈更新 ====================

@tender_bp.route('/<int:tid>/feedbacks', methods=['GET'])
@token_required
def list_feedbacks(tid):
    _ensure_tables()
    rows = get_db().execute("""
        SELECT id, role, content, created_by_name, created_at
        FROM tender_feedbacks WHERE doc_id=? ORDER BY id
    """, (tid,)).fetchall()
    return jsonify({'code': 200, 'message': 'success', 'data': [dict(r) for r in rows]})


@tender_bp.route('/<int:tid>/refine', methods=['POST'])
@token_required
def refine_tender(tid):
    """对话式反馈：用户补充信息（如新增业绩、报价约束），AI 基于反馈更新研判结果。"""
    _ensure_tables()
    payload = request.current_user
    username = payload['username']
    data = request.get_json(silent=True) or {}
    feedback = (data.get('feedback') or '').strip()
    if not feedback:
        return jsonify({'code': 400, 'message': '请输入反馈内容', 'data': None})
    if len(feedback) > 2000:
        return jsonify({'code': 400, 'message': '反馈内容过长（限2000字）', 'data': None})

    db = get_db()
    row = db.execute("SELECT * FROM tender_docs WHERE id=?", (tid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '文件不存在', 'data': None})
    if not row['analysis_result']:
        return jsonify({'code': 400, 'message': '请先完成 AI 研判，再提交反馈', 'data': None})
    if row['status'] == 'analyzing':
        return jsonify({'code': 400, 'message': '正在分析中，请稍候', 'data': None})

    try:
        old_analysis = json.loads(row['analysis_result'])
    except (ValueError, TypeError):
        return jsonify({'code': 400, 'message': '原研判结果异常，请重新研判', 'data': None})

    # 对话历史（最多带最近 10 轮，控制 token）
    history = db.execute("""
        SELECT role, content FROM tender_feedbacks WHERE doc_id=? ORDER BY id DESC LIMIT 20
    """, (tid,)).fetchall()
    history = list(reversed(history))

    quals_hint, _qm = _load_qualification_context(db)

    # 历史对话拼入 user 消息，让 LLM 看到完整反馈脉络
    history_text = ''
    if history:
        lines = []
        for h in history:
            speaker = '我方反馈' if h['role'] == 'user' else 'AI回应'
            lines.append(f"[{speaker}] {h['content'][:400]}")
        history_text = '【历史反馈记录】\n' + '\n'.join(lines) + '\n\n'

    prompt = f"""以下是某采购项目的既有研判报告 JSON，以及我方（研究院）补充反馈的信息。请吸收反馈内容，对研判报告做针对性更新。

{quals_hint}

【既有研判报告 JSON】
{json.dumps(old_analysis, ensure_ascii=False)}

{history_text}【本次新反馈】
{feedback}

更新要求：
1. 反馈中提供的新事实（如业绩、人员、资质、成本底线、报价约束等）必须吸收进报告：资格符合性、能力匹配、得分预估、建议报价、风险点、综合结论等受影响部分同步更新；
2. 反馈与既有判断冲突时，以反馈为准（反馈代表我方掌握的最新真实情况），并在 conclusion.reason 中体现调整依据；
3. 不受反馈影响的部分保持原内容不变；JSON 字段结构与原报告完全一致，不要增删字段；
4. 反馈为提问性质时（如"某条怎么理解"），不改结论，把解答写进 conclusion.reason 末尾；
5. 只返回更新后的完整 JSON，不要输出其他内容。"""

    db.execute("UPDATE tender_docs SET status='analyzing', error_msg=NULL WHERE id=?", (tid,))
    db.commit()
    try:
        from qa_engine import call_llm
        resp = call_llm(
            [{'role': 'system', 'content': '你是资深投标评审专家。根据用户反馈更新投标研判报告，保持JSON结构不变，只返回JSON。'},
             {'role': 'user', 'content': prompt}],
            max_tokens=8192,
            timeout=300,
        )
        if not resp:
            raise RuntimeError('LLM 服务不可用')

        content = resp['choices'][0]['message']['content'] if isinstance(resp, dict) and resp.get('choices') else str(resp)
        result = _parse_llm_json(content)
        if not result or 'project_overview' not in result:
            raise RuntimeError('AI 返回格式异常，请重试')

        # 保留数据源信息，反馈轮次+1
        old_sources = old_analysis.get('_sources') or {}
        old_sources['feedback_rounds'] = (old_sources.get('feedback_rounds') or 0) + 1
        result['_sources'] = old_sources
        db.execute("""
            UPDATE tender_docs SET status='analyzed', analysis_result=?, analyzed_at=?
            WHERE id=?
        """, (json.dumps(result, ensure_ascii=False), _now_str(), tid))
        # 写入对话历史：用户反馈 + AI 摘要
        ai_summary = (result.get('conclusion') or {}).get('reason') or '已根据反馈更新研判报告'
        db.execute("""
            INSERT INTO tender_feedbacks (doc_id, role, content, created_by, created_by_name, created_at)
            VALUES (?, 'user', ?, ?, ?, ?)
        """, (tid, feedback, username, payload.get('name'), _now_str()))
        db.execute("""
            INSERT INTO tender_feedbacks (doc_id, role, content, created_by, created_by_name, created_at)
            VALUES (?, 'assistant', ?, ?, 'AI研判', ?)
        """, (tid, ai_summary, username, _now_str()))
        db.commit()
        record_operation_log(username, '反馈更新', '招标文件', row['filename'])
        return jsonify({'code': 200, 'message': '已根据反馈更新研判报告', 'data': result})
    except Exception as e:
        logger.exception(f'反馈更新研判失败 id={tid}: {e}')
        db.execute("UPDATE tender_docs SET status='analyzed', error_msg=? WHERE id=?",
                   (str(e)[:480], tid))
        db.commit()
        return jsonify({'code': 500, 'message': f'更新失败：{e}', 'data': None})
