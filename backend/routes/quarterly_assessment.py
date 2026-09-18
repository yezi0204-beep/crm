# -*- coding: utf-8 -*-
"""应用中心季度绩效考核（2026方案）——导入制。
蓝图: quarterly_assessment_bp, url_prefix=/api/quarterly-assessment

流程：主任/院长导入成员填写的电子版考核表(xlsx/docx) → 系统自动汇总该成员本季度
系统数据（新签合同/验收/回款） → LLM 分析生成初步考核建议（四维度得分/总分/等级/系数/理由）
→ 考核小组在系统内核定（逐项核定分+约束条件+系数），报人力备案。

维度: 1重点任务50 / 2日常工作30 / 3责任担当与协同10 / 4工作量与饱和度10
约束: 系数>1.0仅限急难险重且S级；低级错误/重大失误≤0.5；市场指标达成≥1；保密隐患≤0.8、事故≤0.5
"""
import csv
import io
import json
import os
import re
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from extensions import get_db, token_required, record_operation_log, user_can, UPLOAD_DIR, DB_PATH
from llm_gateway import gateway_chat

quarterly_assessment_bp = Blueprint('quarterly_assessment', __name__)

APP_DEPT = '应用中心'
DIM_MAX = {1: 50.0, 2: 30.0, 3: 10.0, 4: 10.0}
DIM_NAMES = {1: '重点任务完成情况', 2: '日常工作完成情况', 3: '责任担当与协同贡献', 4: '工作量与任务饱和度'}
VALID_QUARTERS = (1, 2, 3)

GRADE_RULES = {
    'S': (96, 100, 1.0, 1.5),
    'A': (86, 95, 1.0, 1.0),
    'B': (76, 85, 0.8, 1.0),
    'C': (60, 75, 0.6, 0.8),
    'D': (0, 59, 0.0, 0.6),
}


def grade_of(score):
    if score is None:
        return None
    s = float(score)
    if s >= 96:
        return 'S'
    if s >= 86:
        return 'A'
    if s >= 76:
        return 'B'
    if s >= 60:
        return 'C'
    return 'D'


def _ensure_tables():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS quarterly_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            year INTEGER NOT NULL,
            quarter INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',
            self_total REAL DEFAULT 0,
            final_total REAL,
            grade TEXT,
            coefficient REAL,
            constraint_flags TEXT,
            review_comment TEXT,
            reviewed_by TEXT,
            reviewed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_qa_user_period
            ON quarterly_assessments(username, year, quarter);
        CREATE TABLE IF NOT EXISTS quarterly_assessment_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assessment_id INTEGER NOT NULL,
            dimension INTEGER NOT NULL,
            task_name TEXT DEFAULT '',
            difficulty REAL DEFAULT 1.0,
            target TEXT DEFAULT '',
            self_score REAL DEFAULT 0,
            self_note TEXT DEFAULT '',
            evidence TEXT DEFAULT '',
            final_score REAL,
            sort_order INTEGER DEFAULT 0
        );
    """)
    # 导入制扩展字段
    for col, decl in [
        ('suggestion_total', 'REAL'),
        ('suggestion_grade', 'TEXT'),
        ('suggestion_coefficient', 'REAL'),
        ('suggestion_reason', 'TEXT'),
        ('import_file', 'TEXT'),
        ('content', 'TEXT'),
    ]:
        try:
            db.execute(f"ALTER TABLE quarterly_assessments ADD COLUMN {col} {decl}")
        except Exception:
            pass
    db.execute("""
        CREATE TABLE IF NOT EXISTS dept_annual_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL,
            name TEXT NOT NULL,
            target_value REAL,
            actual_value REAL,
            sort_order INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(year, name)
        )
    """)
    db.commit()


def _can_review(username):
    return user_can(username, 'appraisal.view')


def _load_items(cursor, assessment_id):
    cursor.execute(
        "SELECT * FROM quarterly_assessment_items WHERE assessment_id=? ORDER BY dimension, sort_order, id",
        (assessment_id,))
    return [dict(r) for r in cursor.fetchall()]


def _validate_scores(items, field):
    """items 须含 dimension 字段。校验各维度合计不超分值、总分不超100。"""
    dim_sum = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    for it in items:
        dim = int(it.get('dimension') or 0)
        if dim not in DIM_MAX:
            return 0, '存在非法考核维度'
        v = it.get(field)
        if v in (None, ''):
            v = 0
        try:
            v = round(float(v), 2)
        except (TypeError, ValueError):
            return 0, '得分必须为数字'
        if v < 0:
            return 0, '得分不能为负数'
        dim_sum[dim] += v
    for dim, mx in DIM_MAX.items():
        if dim_sum[dim] > mx + 1e-9:
            return 0, f'「{DIM_NAMES[dim]}」合计 {dim_sum[dim]:g} 分，超过该维度上限 {mx:g} 分'
    total = round(sum(dim_sum.values()), 2)
    if total > 100 + 1e-9:
        return 0, '考核总分不能超过100分'
    return total, None


def _validate_coefficient(score, coeff, flags):
    grade = grade_of(score)
    lo, hi, c_lo, c_hi = GRADE_RULES[grade]
    cap = c_hi
    if flags.get('security_hidden'):
        cap = min(cap, 0.8)
    if flags.get('major_mistake') or flags.get('security_accident'):
        cap = min(cap, 0.5)
    floor = 1.0 if flags.get('market_target_met') else c_lo
    if floor > cap + 1e-9:
        if flags.get('market_target_met'):
            reason = f'市场指标达成要求系数≥1，但当前上限为 {cap:g}'
        else:
            reason = f'等级 {grade} 要求系数下限 {c_lo:g}，但约束上限为 {cap:g}'
        return grade, (f'约束冲突：{reason}'
                       f'（等级{grade}系数区间({c_lo:g},{c_hi:g}]'
                       + ('、安全保密/失误约束' if cap < c_hi else '') + '），请核对分数或勾选项')
    try:
        c = round(float(coeff), 2)
    except (TypeError, ValueError):
        return grade, '考核系数必须为数字'
    if c < floor - 1e-9:
        return grade, f'考核系数 {c:g} 低于下限 {floor:g}' + ('（市场指标达成要求≥1）' if flags.get('market_target_met') else '')
    if c > cap + 1e-9:
        if cap < c_hi:
            return grade, f'考核系数 {c:g} 超过约束上限 {cap:g}（安全保密/失误约束）'
        return grade, f'考核系数 {c:g} 超出等级 {grade} 的系数区间({c_lo:g},{c_hi:g}]'
    return grade, None


# ==================== 文档解析 ====================

def _extract_doc_text(filename, data):
    """从 xlsx/docx/csv/txt 提取全文文本。"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in ('.xlsx', '.xlsm'):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
        parts = []
        for ws in wb.worksheets:
            parts.append(f'【工作表:{ws.title}】')
            for row in ws.iter_rows(values_only=True):
                cells = ['' if c is None else str(c).strip() for c in row]
                if any(cells):
                    parts.append(' | '.join(cells).rstrip(' |'))
        wb.close()
        return '\n'.join(parts)
    if ext == '.docx':
        import docx as pydocx
        d = pydocx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for tb in d.tables:
            for row in tb.rows:
                cells = [c.text.strip() for c in row.cells]
                if any(cells):
                    parts.append(' | '.join(cells).rstrip(' |'))
        return '\n'.join(parts)
    if ext in ('.csv', '.txt'):
        for enc in ('utf-8-sig', 'gb18030', 'utf-8'):
            try:
                return data.decode(enc)
            except Exception:
                continue
        return data.decode('utf-8', errors='replace')
    return None


def _quarter_months(year, quarter):
    m0 = (quarter - 1) * 3 + 1
    return [f'{year:04d}-{m0:02d}', f'{year:04d}-{m0+1:02d}', f'{year:04d}-{m0+2:02d}']


def _collect_system_data(cur, members, year, quarter):
    """汇总每个成员本季度系统数据（新签/验收/回款+年度回款目标完成率）。返回 {username: 摘要文本}。"""
    start = f'{year:04d}-{(quarter-1)*3+1:02d}-01'
    end = f'{year:04d}-{(quarter-1)*3+3:02d}-31'
    q_end_month = quarter * 3
    out = {}
    rates = {}
    for m in members:
        uname = m['username']
        cur.execute("""
            SELECT COUNT(*) cnt, COALESCE(SUM(c.total_amt),0) amt
            FROM contracts c
            WHERE c.owner_id=? AND COALESCE(c.is_framework,0)=0
              AND substr(c.sign_date,1,10) BETWEEN ? AND ?
        """, (uname, start, end))
        r = cur.fetchone()
        new_cnt, new_amt = r['cnt'], float(r['amt'] or 0)
        cur.execute("""
            SELECT COALESCE(SUM(a.acceptance_amount),0) amt
            FROM contract_acceptances a JOIN contracts c ON a.contract_id=c.id
            WHERE c.owner_id=? AND substr(a.acceptance_date,1,10) BETWEEN ? AND ?
        """, (uname, start, end))
        acc_amt = float(cur.fetchone()['amt'] or 0)
        cur.execute("""
            SELECT COALESCE(SUM(p.amount),0) amt
            FROM payment_records p JOIN contracts c ON p.contract_id=c.id
            WHERE c.owner_id=? AND substr(p.payment_date,1,10) BETWEEN ? AND ?
        """, (uname, start, end))
        pay_amt = float(cur.fetchone()['amt'] or 0)
        s = (f'本季度新签合同 {new_cnt} 份、合计 {new_amt/10000:.2f} 万元；'
             f'本季度累计验收 {acc_amt/10000:.2f} 万元；本季度累计回款 {pay_amt/10000:.2f} 万元')
        # 年度累计回款目标完成率（月度目标为累计口径）
        cur.execute("SELECT target_amount FROM monthly_targets WHERE username=? AND year=? AND month=?",
                    (uname, year, q_end_month))
        tr = cur.fetchone()
        if tr and tr['target_amount']:
            tgt = float(tr['target_amount'])
            cur.execute("""
                SELECT COALESCE(SUM(p.amount),0) amt
                FROM payment_records p JOIN contracts c ON p.contract_id=c.id
                WHERE c.owner_id=? AND substr(p.payment_date,1,7) <= ?
            """, (uname, f'{year:04d}-{q_end_month:02d}'))
            cum = float(cur.fetchone()['amt'] or 0)
            rate = cum / tgt * 100 if tgt else 0
            s += (f'；{year}年累计回款目标（截至{q_end_month}月）{tgt/10000:.2f} 万元，'
                  f'实际累计回款 {cum/10000:.2f} 万元，完成率 {rate:.1f}%')
        else:
            s += f'；无{year}年个人回款目标记录'
        # 本季度拜访排班与商机跟进
        cur.execute("""
            SELECT COUNT(*) cnt, COUNT(DISTINCT cust_id) cust_cnt,
                   SUM(CASE WHEN work_type='visit' THEN 1 ELSE 0 END) visit_cnt,
                   SUM(CASE WHEN work_type!='visit' THEN 1 ELSE 0 END) other_cnt
            FROM visits WHERE visitor_id=? AND substr(plan_date,1,10) BETWEEN ? AND ?
        """, (uname, start, end))
        vr = cur.fetchone()
        v_cnt, v_cust = vr['cnt'] or 0, vr['cust_cnt'] or 0
        v_visit, v_other = vr['visit_cnt'] or 0, vr['other_cnt'] or 0
        s += (f'；本季度拜访排班 {v_cnt} 次（涉及客户 {v_cust} 家，'
              f'客户拜访 {v_visit} 次、其他 {v_other} 次）')
        # 商机跟进日志（本季度）
        cur.execute("""
            SELECT COUNT(*) cnt FROM follow_logs
            WHERE user_id=? AND ref_type='business' AND substr(log_time,1,10) BETWEEN ? AND ?
        """, (uname, start, end))
        f_cnt = cur.fetchone()['cnt'] or 0
        # 在跟商机情况（当前 active 状态）
        cur.execute("""
            SELECT COUNT(*) cnt, COALESCE(SUM(amount),0) amt,
                   GROUP_CONCAT(DISTINCT stage) stages
            FROM business WHERE owner_id=? AND status='active'
        """, (uname,))
        br = cur.fetchone()
        b_cnt = br['cnt'] or 0
        b_amt = float(br['amt'] or 0)
        s += (f'；本季度商机跟进记录 {f_cnt} 条；当前在跟商机 {b_cnt} 个、'
              f'预计金额合计 {b_amt/10000:.2f} 万元')
        # 本季度商机阶段进展（有跟进日志的商机阶段分布）
        cur.execute("""
            SELECT b.stage, COUNT(DISTINCT b.id) cnt
            FROM business b
            JOIN follow_logs fl ON fl.ref_type='business' AND fl.ref_id=b.id
            WHERE fl.user_id=? AND b.owner_id=? AND substr(fl.log_time,1,10) BETWEEN ? AND ?
            GROUP BY b.stage ORDER BY cnt DESC
        """, (uname, uname, start, end))
        stage_list = [f"{r['stage']}({r['cnt']})" for r in cur.fetchall()]
        if stage_list:
            s += f'；本季度有跟进的商机阶段分布：{"、".join(stage_list)}'
        out[uname] = s
        # 个人回款完成率（结构化，供服务端校准）
        if tr and tr['target_amount']:
            tgt = float(tr['target_amount'])
            cur.execute("""
                SELECT COALESCE(SUM(p.amount),0) amt
                FROM payment_records p JOIN contracts c ON p.contract_id=c.id
                WHERE c.owner_id=? AND substr(p.payment_date,1,7) <= ?
            """, (uname, f'{year:04d}-{q_end_month:02d}'))
            cum = float(cur.fetchone()['amt'] or 0)
            rates[uname] = round(cum / tgt * 100, 1) if tgt else None
        else:
            rates[uname] = None
    return out, rates


def _load_dept_targets(cur, year):
    """读取部门年度指标（含完成率），返回 (指标文本, 指标行列表)。"""
    cur.execute("SELECT name, target_value, actual_value FROM dept_annual_targets "
                "WHERE year=? ORDER BY sort_order, id", (year,))
    rows = [dict(r) for r in cur.fetchall()]
    lines = []
    for r in rows:
        tgt, act = r['target_value'], r['actual_value']
        if tgt and act is not None:
            rate = float(act) / float(tgt) * 100
            lines.append(f"{r['name']}: 目标 {float(tgt):g}，完成 {float(act):g}，完成率 {rate:.1f}%")
        elif tgt:
            lines.append(f"{r['name']}: 目标 {float(tgt):g}，完成值未填报")
        else:
            lines.append(f"{r['name']}: 未设目标")
    return ('\n'.join(lines) if lines else '（未配置部门年度指标）'), rows


def _dept_min_rate(rows):
    """部门各指标完成率的最小值（%），无有效指标返回 None。"""
    rates = [float(r['actual_value']) / float(r['target_value']) * 100
             for r in rows if r.get('target_value') and r.get('actual_value') is not None]
    return min(rates) if rates else None


# ==================== 接口 ====================

@quarterly_assessment_bp.route('/import', methods=['POST'])
@token_required
def import_assessments():
    """上传电子版考核表(xlsx/docx/csv) → 解析 → 系统数据汇总 → LLM 初步考核建议。"""
    payload = request.current_user
    if not _can_review(payload['username']):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    year = int(request.form.get('year') or datetime.now().year)
    quarter = int(request.form.get('quarter') or 0)
    if quarter not in VALID_QUARTERS:
        return jsonify({'code': 400, 'message': '考核周期仅限前三季度', 'data': None})
    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'code': 400, 'message': '请选择考核表文件', 'data': None})
    data = file.read()
    text = _extract_doc_text(file.filename, data)
    if not text:
        return jsonify({'code': 400, 'message': f'仅支持 xlsx/docx/csv/txt 格式：{file.filename}', 'data': None})

    # 原文件留存，便于追溯查看
    save_dir = os.path.join(UPLOAD_DIR, 'quarterly_assessment', str(year), f'Q{quarter}')
    os.makedirs(save_dir, exist_ok=True)
    safe_name = f"{datetime.now().strftime('%H%M%S')}_{os.path.basename(file.filename)}"
    save_path = os.path.join(save_dir, safe_name)
    with open(save_path, 'wb') as f:
        f.write(data)
    rel_path = f'quarterly_assessment/{year}/Q{quarter}/{safe_name}'

    db = get_db()
    cur = db.cursor()
    # 部门主任不参与员工考核
    cur.execute("SELECT username, name, role FROM users WHERE department=? AND status='在职' AND role!='主任'",
                (APP_DEPT,))
    members = [dict(r) for r in cur.fetchall()]
    sys_data, personal_rates = _collect_system_data(cur, members, year, quarter)
    dept_text, dept_rows = _load_dept_targets(cur, year)
    dept_min_rate = _dept_min_rate(dept_rows)

    suggestion = _run_llm_analysis(payload['username'], text, year, quarter, members, sys_data, dept_text)
    if not suggestion or not isinstance(suggestion.get('members'), list) or not suggestion['members']:
        return jsonify({'code': 422, 'message':
                        '文档解析成功，但大模型分析失败（服务不可用或返回异常）。请检查LLM配置后重试。',
                        'data': None})

    name2user = {m['name']: m for m in members}
    results, skipped = _apply_suggestion(db, suggestion, name2user, year, quarter, rel_path, text, sys_data,
                                         dept_min_rate=dept_min_rate, personal_rates=personal_rates)
    db.commit()
    record_operation_log(payload['username'], '导入', '季度考核',
                         f'导入{year}年第{quarter}季度考核表「{file.filename}」，LLM生成{len(results)}人初步建议')
    return jsonify({'code': 200, 'message': f'导入完成：{len(results)}人生成初步考核建议', 'data': {
        'filename': file.filename, 'results': results, 'skipped': skipped,
    }})


def _run_llm_analysis(operator, text, year, quarter, members, sys_data, dept_text):
    """构建 prompt 并调用 LLM，返回解析后的建议 dict 或 None。"""
    sys_summary = '\n'.join(f"- {m['name']}({m['role']})：{sys_data[m['username']]}" for m in members)
    rule_text = (
        '考核维度及分值：重点任务完成情况50分、日常工作完成情况30分、责任担当与协同贡献10分、工作量与任务饱和度10分。\n'
        '等级：96-100为S(系数1.0~1.5]、86-95为A(系数1.0)、76-85为B(系数0.8~1.0)、60-75为C(系数0.6~0.8]、0-59为D(系数0~0.6]。\n'
        '约束：系数>1.0仅限承担急难险重任务且业绩贡献特别显著；出现低级错误或重大失误系数≤0.5；'
        '完成市场指标系数≥1；安全保密隐患≤0.8、安全保密事故≤0.5。'
    )
    value_text = (
        '【工作价值横向判断原则（极其重要）】\n'
        '1. 任务是成员自己设定的，绝对不能因为"完成了自填任务"就给高分，必须横向判断任务本身的价值。\n'
        '2. 工作价值优先级（从高到低）：\n'
        '   - 第一档（直接产出业绩）：签订合同、完成验收、实现回款——这是部门核心指标，价值最高。\n'
        '   - 第二档（推进业绩转化）：推进商机到后期阶段（方案报价/商务谈判/合同签订阶段）、高质量客户拜访并促成商机进展。\n'
        '   - 第三档（过程性工作）：初步洽谈/需求引导阶段的商机跟进、常规客户拜访、内部支撑与协同。\n'
        '   - 第四档（事务性工作）：会议、培训、文档整理、日常行政等，价值最低，即使完成也不能因此拿高分。\n'
        '3. 评分时须对照系统数据：若成员本季度新签合同/验收/回款为零或极少，即使自填任务全部完成，'
        '「重点任务完成情况」也不得给高分（销售/市场类岗位原则上不超过30分，综合支撑岗不超过40分）。\n'
        '4. 必须结合系统中的拜访排班和商机跟进记录评估：拜访次数多但商机无进展，不能视为高价值工作；'
        '商机跟进应看阶段是否推进（从初步接触→引导需求→方案报价→商务谈判→合同签订），而非仅看跟进次数。\n'
        '5. 横向比较：同一岗位的成员之间，谁的合同/回款/验收多、商机推进更深入，谁的重点任务得分应更高，'
        '不能出现业绩差者反而得分高的倒挂情况。'
    )
    calibration_text = (
        '【评分校准规则（必须严格执行，系统数据优先于个人自评）】\n'
        '1. 部门联动（最高优先级）：部门年度指标完成率<100%时，全体成员考核系数一律不得≥1.0'
        '（建议上限0.9），不得评S级；个人自评再好、个人指标再超额也不能突破此上限。\n'
        '2. 部门完成率<60%时：市场/销售类岗位「重点任务完成情况」得分原则上不超过50分的60%（30分），'
        '总分原则上不超过85分（不得评S/A级），考核系数建议≤0.8；研发/综合支撑岗位相应从严，'
        '可结合岗位性质酌情掌握，但系数同样<1.0。\n'
        '3. 部门完成率60%~100%时：整体从严评分，不得评S级，A级仅限个人指标达成且业绩贡献特别显著者，系数上限0.9。\n'
        '4. 部门完成率≥100%时：个人对应时间节点市场指标达成者考核系数方可≥1；未达成者系数应<1。\n'
        '5. 个人回款指标完成率<60%者：总分原则上不得进入S/A档，建议系数≤0.8。\n'
        '6. 若下方未列出部门指标（未配置），以个人回款指标完成率为主要校准依据（完成率<100%者系数应<1）。'
    )
    prompt = f"""你是应用中心绩效考核小组的助理分析师。以下是员工填写的{year}年第{quarter}季度（1-3月/4-6月/7-9月）电子版个人季度绩效考核表内容，以及CRM系统中各成员的业绩数据和部门年度指标完成情况。

【考核规则】
{rule_text}

{value_text}

{calibration_text}

【部门年度指标完成度】
{dept_text}

【系统数据】（含本季度新签合同/验收/回款、拜访排班次数与客户数、商机跟进记录数与阶段分布；供交叉校验，文档自评与系统数据明显不符时应提示）
{sys_summary}

【考核表内容】
{text[:20000]}

请为考核表中出现的每一位成员生成初步考核建议，严格按以下JSON格式输出，不要输出其他内容：
{{"members":[{{"name":"成员姓名","items":[{{"dimension":1,"task_name":"任务名","target":"目标/交付物","difficulty":1.0,"self_score":48,"self_note":"完成情况","evidence":"佐证"}}],"dim_scores":{{"1":48,"2":28,"3":9,"4":9}},"total":94,"grade":"A","coefficient":1.0,"reason":"评分理由（必须结合系统数据中的合同/回款/验收、拜访排班、商机跟进进展，以及部门指标完成度说明评分依据，200字内）"}}]}}
要求：
1. items 中的 dimension 取值 1/2/3/4 对应上述四个维度；difficulty 为难度系数(0.5~3)；self_score 为该项建议得分。
2. dim_scores 为四个维度的建议得分合计（不得超过维度上限：1→50、2→30、3→10、4→10）。
3. total=四维度合计，grade 与 total 对应，coefficient 符合该等级区间与约束，并符合上方校准规则。
4. 仅分析文档中实际出现的成员；成员姓名须能对应系统数据中的姓名。
5. 评分必须结合系统数据中的拜访排班和商机跟进记录，不得以"完成了自填任务"作为高分依据；同岗位成员间须横向比较业绩产出。"""

    resp_text = gateway_chat(
        [{'role': 'user', 'content': prompt}],
        max_tokens=8000, timeout=300, operation_type='assessment_suggest',
        data_source='quarterly_assessment', operator=operator)
    if not resp_text:
        return None
    m = re.search(r'\{[\s\S]*\}', resp_text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _calibrate(total, grade, coeff, dept_min_rate, personal_rate):
    """服务端硬校准：部门/个人指标完成度强制约束（LLM 输出不得突破）。"""
    notes = []
    if dept_min_rate is not None and dept_min_rate < 60:
        if total > 85:
            total = 85.0
            notes.append(f'部门指标完成率{dept_min_rate:.1f}%<60%，总分强制降至85分')
        if coeff is None or coeff > 0.8:
            coeff = 0.8
            notes.append('系数强制≤0.8')
    elif dept_min_rate is not None and dept_min_rate < 100:
        if total > 95:
            total = 95.0
            notes.append(f'部门指标完成率{dept_min_rate:.1f}%<100%，不得评S级，总分强制降至95分')
        if coeff is None or coeff > 0.9:
            coeff = 0.9
            notes.append('系数强制≤0.9')
    elif dept_min_rate is not None and dept_min_rate >= 100:
        if personal_rate is not None and personal_rate < 100 and (coeff is None or coeff >= 1):
            coeff = 0.9
            notes.append('个人指标未达成，系数强制<1.0')
    else:
        # 未配置部门指标：以个人回款完成率校准
        if personal_rate is not None and personal_rate < 60:
            if total > 85:
                total = 85.0
                notes.append(f'个人回款完成率{personal_rate:.1f}%<60%，总分强制降至85分')
            if coeff is None or coeff > 0.8:
                coeff = 0.8
                notes.append('系数强制≤0.8')
        elif personal_rate is not None and personal_rate < 100 and (coeff is None or coeff >= 1):
            coeff = 0.9
            notes.append(f'个人回款完成率{personal_rate:.1f}%<100%，系数强制<1.0')
    # 个人完成率<60% 的叠加约束（任何部门档位下都适用）
    if personal_rate is not None and personal_rate < 60 and total > 85:
        total = 85.0
        notes.append(f'个人回款完成率{personal_rate:.1f}%<60%，总分强制降至85分')
        if coeff is None or coeff > 0.8:
            coeff = 0.8
            notes.append('系数强制≤0.8')
    new_grade = grade_of(total)
    if grade and new_grade != grade:
        notes.append(f'等级由 {grade} 校正为 {new_grade}')
    return total, new_grade, coeff, ('；'.join(notes) if notes else '')


def _apply_suggestion(conn, suggestion, name2user, year, quarter, rel_path, text, sys_data,
                      dept_min_rate=None, personal_rates=None):
    """把 LLM 建议落库（同季度覆盖），返回 (results, skipped)。"""
    cur = conn.cursor()
    results, skipped = [], []
    for mem in suggestion.get('members') or []:
        name = (mem.get('name') or '').strip().replace(' ', '')
        user = name2user.get(name)
        if not user:
            for n, m in name2user.items():
                if n and (n in name or name in n):
                    user = m
                    break
        if not user:
            skipped.append(name)
            continue
        items = []
        for i, it in enumerate(mem.get('items') or []):
            dim = int(it.get('dimension') or 0)
            if dim not in DIM_MAX:
                continue
            items.append({
                'dimension': dim,
                'task_name': (it.get('task_name') or '').strip(),
                'difficulty': float(it.get('difficulty') or 1.0),
                'target': (it.get('target') or '').strip(),
                'self_score': round(float(it.get('self_score') or 0), 2),
                'self_note': (it.get('self_note') or '').strip(),
                'evidence': (it.get('evidence') or '').strip(),
                'sort_order': i,
            })
        if not items:
            skipped.append(name)
            continue
        ds = mem.get('dim_scores') or {}
        dim_total = sum(DIM_MAX[int(k)] if float(ds.get(k) or 0) > DIM_MAX[int(k)] else float(ds.get(k) or 0)
                        for k in ds if str(k) in {'1', '2', '3', '4'})
        total = round(float(mem.get('total') or dim_total), 2)
        grade = (mem.get('grade') or grade_of(total) or '').strip().upper()
        try:
            coeff = round(float(mem.get('coefficient')), 2)
        except (TypeError, ValueError):
            coeff = None
        reason = (mem.get('reason') or '').strip()
        # 服务端硬校准：部门/个人指标完成度强制约束
        p_rate = (personal_rates or {}).get(user['username'])
        total, grade, coeff, cal_note = _calibrate(total, grade, coeff, dept_min_rate, p_rate)
        if cal_note:
            reason = (reason + '【系统校准】' + cal_note).strip()
        # 落库：同季度重导入覆盖
        cur.execute("SELECT id FROM quarterly_assessments WHERE username=? AND year=? AND quarter=?",
                    (user['username'], year, quarter))
        row = cur.fetchone()
        if row:
            aid = row['id']
            cur.execute("DELETE FROM quarterly_assessment_items WHERE assessment_id=?", (aid,))
        else:
            cur.execute("INSERT INTO quarterly_assessments(username,year,quarter,status) VALUES(?,?,?,'draft')",
                        (user['username'], year, quarter))
            aid = cur.lastrowid
        for i, it in enumerate(items):
            cur.execute("""
                INSERT INTO quarterly_assessment_items
                (assessment_id, dimension, task_name, difficulty, target, self_score, self_note, evidence, sort_order)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (aid, it['dimension'], it['task_name'], it['difficulty'], it['target'],
                  it['self_score'], it['self_note'], it['evidence'], it['sort_order']))
        cur.execute("""
            UPDATE quarterly_assessments SET self_total=?, suggestion_total=?, suggestion_grade=?,
                suggestion_coefficient=?, suggestion_reason=?, import_file=?, content=?,
                updated_at=CURRENT_TIMESTAMP WHERE id=?
        """, (total, total, grade, coeff, reason, rel_path, text[:20000], aid))
        results.append({'username': user['username'], 'name': user['name'],
                        'total': total, 'grade': grade, 'coefficient': coeff,
                        'items': len(items), 'system_data': sys_data[user['username']],
                        'reason': reason, 'import_file': rel_path})
    conn.commit()
    return results, skipped


@quarterly_assessment_bp.route('/file/<int:assessment_id>', methods=['GET'])
@token_required
def download_import_file(assessment_id):
    """下载导入的原始考核表。"""
    payload = request.current_user
    if not _can_review(payload['username']):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT import_file FROM quarterly_assessments WHERE id=?", (assessment_id,))
    row = cur.fetchone()
    if not row or not row['import_file']:
        return jsonify({'code': 404, 'message': '无导入文件', 'data': None})
    full = os.path.join(UPLOAD_DIR, row['import_file'].replace('/', os.sep))
    if not os.path.exists(full):
        return jsonify({'code': 404, 'message': '文件已不存在', 'data': None})
    return send_file(full, as_attachment=True, download_name=os.path.basename(full))


@quarterly_assessment_bp.route('/dept-targets', methods=['GET'])
@token_required
def get_dept_targets():
    """部门年度指标（考核小组可管理）。"""
    payload = request.current_user
    if not _can_review(payload['username']):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    year = int(request.args.get('year') or datetime.now().year)
    db = get_db()
    cur = db.cursor()
    _, rows = _load_dept_targets(cur, year)
    return jsonify({'code': 200, 'message': 'success', 'data': {'rows': rows}})


@quarterly_assessment_bp.route('/dept-targets', methods=['PUT'])
@token_required
def save_dept_targets():
    """保存部门年度指标（整表覆盖）。body: {year, rows:[{name,target_value,actual_value}]}"""
    payload = request.current_user
    if not _can_review(payload['username']):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    body = request.get_json(silent=True) or {}
    year = int(body.get('year') or datetime.now().year)
    rows = body.get('rows') or []
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM dept_annual_targets WHERE year=?", (year,))
    for i, r in enumerate(rows):
        name = (r.get('name') or '').strip()
        if not name:
            continue
        try:
            tgt = round(float(r.get('target_value')), 2) if r.get('target_value') not in (None, '') else None
            act = round(float(r.get('actual_value')), 2) if r.get('actual_value') not in (None, '') else None
        except (TypeError, ValueError):
            return jsonify({'code': 400, 'message': f'指标「{name}」的目标/完成值必须为数字', 'data': None})
        cur.execute("INSERT INTO dept_annual_targets(year,name,target_value,actual_value,sort_order) VALUES(?,?,?,?,?)",
                    (year, name, tgt, act, i))
    db.commit()
    record_operation_log(payload['username'], '配置', '季度考核',
                         f'保存{year}年部门年度指标 {len(rows)} 项')
    return jsonify({'code': 200, 'message': '已保存部门年度指标', 'data': None})


@quarterly_assessment_bp.route('/reanalyze', methods=['POST'])
@token_required
def reanalyze():
    """用已留存的原表文件重跑 LLM 分析（应用最新部门指标与校准规则），覆盖当前季度建议。"""
    payload = request.current_user
    if not _can_review(payload['username']):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    body = request.get_json(silent=True) or {}
    year = int(body.get('year') or datetime.now().year)
    quarter = int(body.get('quarter') or 0)
    if quarter not in VALID_QUARTERS:
        return jsonify({'code': 400, 'message': '考核周期仅限前三季度', 'data': None})

    db = get_db()
    cur = db.cursor()
    cur.execute("""SELECT id, username, import_file FROM quarterly_assessments
                   WHERE year=? AND quarter=? AND import_file IS NOT NULL""", (year, quarter))
    recs = [dict(r) for r in cur.fetchall()]
    if not recs:
        return jsonify({'code': 404, 'message': '当前季度没有已导入的考核表', 'data': None})
    cur.execute("SELECT username, name, role FROM users WHERE department=? AND status='在职' AND role!='主任'",
                (APP_DEPT,))
    members = [dict(r) for r in cur.fetchall()]
    sys_data, personal_rates = _collect_system_data(cur, members, year, quarter)
    dept_text, dept_rows = _load_dept_targets(cur, year)
    dept_min_rate = _dept_min_rate(dept_rows)
    name2user = {m['name']: m for m in members}

    def work(rec):
        full = os.path.join(UPLOAD_DIR, rec['import_file'].replace('/', os.sep))
        fname = os.path.basename(rec['import_file'])
        if not os.path.exists(full):
            return {'assessment_id': rec['id'], 'ok': False, 'error': f'原文件缺失：{fname}'}
        with open(full, 'rb') as f:
            data = f.read()
        text = _extract_doc_text(fname, data)
        if not text:
            return {'assessment_id': rec['id'], 'ok': False, 'error': f'文件解析失败：{fname}'}
        try:
            # 线程内独立连接（WAL 允许并发写，各自提交）
            conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            suggestion = _run_llm_analysis(payload['username'], text, year, quarter, members, sys_data, dept_text)
            if not suggestion or not isinstance(suggestion.get('members'), list) or not suggestion['members']:
                conn.close()
                return {'assessment_id': rec['id'], 'ok': False, 'error': f'LLM分析失败：{fname}'}
            results, skipped = _apply_suggestion(conn, suggestion, name2user, year, quarter,
                                                 rec['import_file'], text, sys_data,
                                                 dept_min_rate=dept_min_rate,
                                                 personal_rates=personal_rates)
            conn.close()
            return {'assessment_id': rec['id'], 'ok': True, 'results': results, 'skipped': skipped}
        except Exception as e:
            return {'assessment_id': rec['id'], 'ok': False, 'error': f'{fname}: {e}'}

    with ThreadPoolExecutor(max_workers=4) as ex:
        file_results = list(ex.map(work, recs))
    ok_cnt = sum(1 for x in file_results if x['ok'])
    record_operation_log(payload['username'], '重新分析', '季度考核',
                         f'{year}年第{quarter}季度重跑LLM考核建议，成功{ok_cnt}/{len(recs)}份')
    return jsonify({'code': 200, 'message': f'重新分析完成：{ok_cnt}/{len(recs)} 份成功', 'data': {
        'files': file_results}})


@quarterly_assessment_bp.route('/mine', methods=['GET'])
@token_required
def my_assessment():
    """登录用户查看自己的季度考核（导入建议+核定结果），只读。"""
    payload = request.current_user
    year = int(request.args.get('year') or datetime.now().year)
    quarter = int(request.args.get('quarter') or 0)
    if quarter not in VALID_QUARTERS:
        m = datetime.now().month
        quarter = 1 if m <= 3 else (2 if m <= 6 else 3)
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM quarterly_assessments WHERE username=? AND year=? AND quarter=?",
                (payload['username'], year, quarter))
    a = cur.fetchone()
    if not a:
        return jsonify({'code': 200, 'message': 'success',
                        'data': {'assessment': None, 'items': [],
                                 'dim_max': DIM_MAX, 'dim_names': DIM_NAMES}})
    items = _load_items(cur, a['id'])
    return jsonify({'code': 200, 'message': 'success', 'data': {
        'assessment': dict(a), 'items': items,
        'dim_max': DIM_MAX, 'dim_names': DIM_NAMES,
    }})


@quarterly_assessment_bp.route('/overview', methods=['GET'])
@token_required
def overview():
    payload = request.current_user
    if not _can_review(payload['username']):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    year = int(request.args.get('year') or datetime.now().year)
    quarter = int(request.args.get('quarter') or 0)
    if quarter not in VALID_QUARTERS:
        m = datetime.now().month
        quarter = 1 if m <= 3 else 2
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT u.username, u.name, u.role,
               a.id AS assessment_id, a.status AS a_status, a.self_total,
               a.final_total, a.grade, a.coefficient, a.review_comment,
               a.suggestion_total, a.suggestion_grade, a.suggestion_coefficient, a.import_file
        FROM users u
        LEFT JOIN quarterly_assessments a
          ON a.username = u.username AND a.year = ? AND a.quarter = ?
        WHERE u.department = ? AND u.status = '在职' AND u.role != '主任'
        ORDER BY u.role DESC, u.username
    """, (year, quarter, APP_DEPT))
    rows = [dict(r) for r in cur.fetchall()]
    return jsonify({'code': 200, 'message': 'success', 'data': {'rows': rows}})


@quarterly_assessment_bp.route('/detail/<username>', methods=['GET'])
@token_required
def detail(username):
    payload = request.current_user
    if username != payload['username'] and not _can_review(payload['username']):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    year = int(request.args.get('year') or datetime.now().year)
    quarter = int(request.args.get('quarter') or 0)
    if quarter not in VALID_QUARTERS:
        return jsonify({'code': 400, 'message': '无效季度', 'data': None})
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM quarterly_assessments WHERE username=? AND year=? AND quarter=?",
                (username, year, quarter))
    a = cur.fetchone()
    if not a:
        return jsonify({'code': 200, 'message': 'success', 'data': {'assessment': None, 'items': []}})
    items = _load_items(cur, a['id'])
    return jsonify({'code': 200, 'message': 'success', 'data': {'assessment': dict(a), 'items': items}})


@quarterly_assessment_bp.route('/review', methods=['POST'])
@token_required
def review():
    payload = request.current_user
    reviewer = payload['username']
    if not _can_review(reviewer):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    year = int(data.get('year') or datetime.now().year)
    quarter = int(data.get('quarter') or 0)
    items = data.get('items') or []
    flags = data.get('constraint_flags') or {}
    coefficient = data.get('coefficient')
    comment = (data.get('review_comment') or '').strip()
    if quarter not in VALID_QUARTERS:
        return jsonify({'code': 400, 'message': '无效季度', 'data': None})
    if not items:
        return jsonify({'code': 400, 'message': '无考核明细可核定', 'data': None})

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM quarterly_assessments WHERE username=? AND year=? AND quarter=?",
                (username, year, quarter))
    a = cur.fetchone()
    if not a:
        return jsonify({'code': 400, 'message': '该员工无此季度考核数据，请先导入', 'data': None})
    a = dict(a)

    for it in items:
        if it.get('final_score') in (None, ''):
            return jsonify({'code': 400, 'message': '请为每项任务填写核定得分', 'data': None})
    stored = {r['id']: r['dimension'] for r in _load_items(cur, a['id'])}
    for it in items:
        if it['id'] not in stored:
            return jsonify({'code': 400, 'message': f'考核明细 ID:{it["id"]} 不存在', 'data': None})
    check_items = [{'dimension': stored[it['id']], 'final_score': it['final_score']} for it in items]
    total, err = _validate_scores(check_items, 'final_score')
    if err:
        return jsonify({'code': 400, 'message': err, 'data': None})
    grade, err = _validate_coefficient(total, coefficient, flags)
    if err:
        return jsonify({'code': 400, 'message': err, 'data': None})

    try:
        for it in items:
            cur.execute("UPDATE quarterly_assessment_items SET final_score=? WHERE id=? AND assessment_id=?",
                        (round(float(it['final_score']), 2), it['id'], a['id']))
        cur.execute("""
            UPDATE quarterly_assessments
            SET status='reviewed', final_total=?, grade=?, coefficient=?,
                constraint_flags=?, review_comment=?, reviewed_by=?, reviewed_at=CURRENT_TIMESTAMP,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (total, grade, round(float(coefficient), 2),
              json.dumps({k: bool(flags.get(k)) for k in
                          ('urgent_task', 'major_mistake', 'security_hidden', 'security_accident', 'market_target_met')},
                         ensure_ascii=False),
              comment, reviewer, a['id']))
        db.commit()
        record_operation_log(reviewer, '核定', '季度考核',
                             f'核定{username} {year}年第{quarter}季度考核：{total:g}分/{grade}级/系数{float(coefficient):g}（ID:{a["id"]}）')
        return jsonify({'code': 200, 'message': f'核定完成：{total:g} 分，等级 {grade}', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@quarterly_assessment_bp.route('/export', methods=['GET'])
@token_required
def export_csv():
    payload = request.current_user
    if not _can_review(payload['username']):
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})
    year = int(request.args.get('year') or datetime.now().year)
    quarter = int(request.args.get('quarter') or 0)
    if quarter not in VALID_QUARTERS:
        return jsonify({'code': 400, 'message': '无效季度', 'data': None})
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT u.name, u.role, u.username,
               a.status, a.self_total, a.suggestion_total, a.suggestion_grade, a.suggestion_coefficient,
               a.final_total, a.grade, a.coefficient, a.review_comment
        FROM users u
        LEFT JOIN quarterly_assessments a
          ON a.username = u.username AND a.year = ? AND a.quarter = ?
        WHERE u.department = ? AND u.status = '在职' AND u.role != '主任'
        ORDER BY u.role DESC, u.username
    """, (year, quarter, APP_DEPT))
    rows = cur.fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['姓名', '角色', '账号', '状态', '建议总分', '建议等级', '建议系数',
                     '核定总分', '等级', '考核系数', '核定意见'])
    for r in rows:
        st = {'draft': '待核定', 'reviewed': '已核定'}.get(r['status'], '未导入')
        fmt = lambda v, suf='': '' if v is None else f'{v:g}{suf}'
        writer.writerow([r['name'], r['role'], r['username'], st,
                         fmt(r['suggestion_total']), r['suggestion_grade'] or '', fmt(r['suggestion_coefficient']),
                         fmt(r['final_total']), r['grade'] or '', fmt(r['coefficient']),
                         (r['review_comment'] or '').replace('\n', ' ')])
    out = io.BytesIO()
    out.write('\ufeff'.encode('utf-8'))
    out.write(buf.getvalue().encode('utf-8'))
    out.seek(0)
    return send_file(out, mimetype='text/csv; charset=utf-8', as_attachment=True,
                     download_name=f'应用中心季度考核_{year}Q{quarter}.csv')


def register_routes(app):
    with app.app_context():
        _ensure_tables()
    app.register_blueprint(quarterly_assessment_bp, url_prefix='/api/quarterly-assessment')
