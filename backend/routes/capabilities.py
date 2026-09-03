"""我方能力模型 API。

公司能力条目：遥感/GIS/农业/林业/水利/生态环境/AI/智能体/大数据/
软件开发/无人机/仿真/雷达等。

GET    /api/capabilities        列表
POST   /api/capabilities        新增
PUT    /api/capabilities/<id>   编辑
DELETE /api/capabilities/<id>   删除
POST   /api/capabilities/match  能力匹配（给定项目需求→匹配能力）
"""
from flask import Blueprint, request, jsonify
from extensions import get_db, token_required, admin_required, record_operation_log
import json
import logging

logger = logging.getLogger(__name__)
capabilities_bp = Blueprint('capabilities', __name__)

DEFAULT_CAPABILITIES = [
    ('遥感', 'mature', '卫星遥感数据处理与应用', '多光谱/高光谱/SAR影像处理', '资源监测/灾害评估解决方案', '自然资源监测平台', '遥感,卫星,影像,监测'),
    ('GIS', 'mature', '地理信息系统开发', '空间数据库/地图服务', 'GIS平台建设', '地理信息平台项目', 'GIS,地理信息,地图,空间'),
    ('农业', 'mature', '智慧农业解决方案', '农情监测/产量预估', '数字农业平台', '农业大数据项目', '农业,农情,种植,耕地'),
    ('林业', 'normal', '林业资源监测', '森林防火/病虫害监测', '智慧林业平台', '林业监测项目', '林业,森林,防火'),
    ('水利', 'normal', '智慧水利解决方案', '水文监测/洪水预警', '数字孪生水利', '水利信息化项目', '水利,水文,洪水,河湖'),
    ('生态环境', 'mature', '生态环境监测', '大气/水/土壤监测分析', '生态保护监管平台', '环保监测项目', '生态环境,环保,污染,生态'),
    ('AI', 'mature', '人工智能算法与应用', '目标检测/变化检测/图像识别', 'AI+行业解决方案', 'AI识别项目', 'AI,人工智能,深度学习,算法'),
    ('智能体', 'growing', 'LLM智能体开发', 'RAG/Agent/工作流', '智能问答系统', '智能体应用项目', '智能体,Agent,大模型,LLM'),
    ('大数据', 'mature', '大数据平台建设', '数据治理/数据仓库/可视化', '数据中台', '大数据平台项目', '大数据,数据中台,数据治理'),
    ('软件开发', 'mature', '行业应用软件开发', 'Web/移动端/桌面端', '定制开发服务', '各类软件开发项目', '软件开发,系统开发,平台开发'),
    ('无人机', 'normal', '无人机遥感应用', '航拍/巡检/测绘', '无人机巡检方案', '无人机应用项目', '无人机,航测,巡检'),
    ('仿真', 'normal', '仿真模拟系统', '数字孪生/训练模拟', '模拟训练平台', '仿真训练项目', '仿真,模拟,数字孪生,训练'),
    ('雷达', 'growing', '雷达数据处理', 'SAR/InSAR形变监测', '雷达监测系统', '雷达应用项目', '雷达,SAR,合成孔径,InSAR'),
]


def register_routes(app):
    app.register_blueprint(capabilities_bp, url_prefix='/api/capabilities')


@capabilities_bp.route('', methods=['GET'])
@token_required
def list_capabilities():
    db = get_db()
    search = request.args.get('search', '').strip()
    enabled = request.args.get('enabled', type=int)

    sql = "SELECT * FROM capabilities WHERE 1=1"
    params = []
    if search:
        sql += " AND (name LIKE ? OR description LIKE ? OR keywords LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    if enabled is not None:
        sql += " AND enabled=?"
        params.append(enabled)

    rows = db.execute(sql + " ORDER BY id", params).fetchall()
    data = []
    for r in rows:
        d = dict(r)
        for f in ('products', 'solutions', 'cases', 'keywords', 'synonyms', 'related_industries'):
            if d.get(f):
                try:
                    d[f] = json.loads(d[f]) if d[f].startswith('[') else [x.strip() for x in d[f].split(',') if x.strip()]
                except (json.JSONDecodeError, TypeError):
                    d[f] = []
            else:
                d[f] = []
        data.append(d)
    return jsonify({'code': 200, 'data': data, 'total': len(data)})


@capabilities_bp.route('', methods=['POST'])
@admin_required
def create_capability():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'code': 400, 'message': '能力名称必填'})
    db = get_db()
    existing = db.execute("SELECT id FROM capabilities WHERE name=?", (name,)).fetchone()
    if existing:
        return jsonify({'code': 400, 'message': f'能力「{name}」已存在'})

    def _arr(key):
        val = data.get(key) or []
        return json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val

    cursor = db.execute("""
        INSERT INTO capabilities (name, level, description, products, solutions,
            cases, keywords, synonyms, related_industries, enabled)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, data.get('level', 'mature'), data.get('description', ''),
          _arr('products'), _arr('solutions'), _arr('cases'),
          _arr('keywords'), _arr('synonyms'), _arr('related_industries'),
          data.get('enabled', 1)))
    db.commit()
    record_operation_log(request.current_user, 'create', 'capability', f'新增能力:{name}')
    return jsonify({'code': 200, 'message': '已新增', 'data': {'id': cursor.lastrowid}})


@capabilities_bp.route('/seed', methods=['POST'])
@admin_required
def seed_capabilities():
    """初始化默认能力（13项，不覆盖已有）。"""
    db = get_db()
    created = 0
    for name, level, desc, products, solutions, cases, keywords in DEFAULT_CAPABILITIES:
        existing = db.execute("SELECT id FROM capabilities WHERE name=?", (name,)).fetchone()
        if existing:
            continue
        db.execute("""
            INSERT INTO capabilities (name, level, description, products, solutions,
                cases, keywords, synonyms, related_industries)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, level, desc, json.dumps([products], ensure_ascii=False),
              json.dumps([solutions], ensure_ascii=False),
              json.dumps([cases], ensure_ascii=False),
              json.dumps(keywords.split(','), ensure_ascii=False), '[]', '[]'))
        created += 1
    db.commit()
    record_operation_log(request.current_user, 'seed', 'capability', f'初始化{created}项默认能力')
    return jsonify({'code': 200, 'message': f'已初始化{created}项默认能力'})


@capabilities_bp.route('/<int:cid>', methods=['PUT'])
@admin_required
def update_capability(cid):
    data = request.get_json(silent=True) or {}
    db = get_db()
    row = db.execute("SELECT id FROM capabilities WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '能力不存在'})

    def _arr(key):
        if key not in data:
            return None
        val = data[key]
        return json.dumps(val, ensure_ascii=False) if isinstance(val, list) else val

    updates, params = [], []
    for f in ('name', 'level', 'description'):
        if f in data:
            updates.append(f'{f}=?')
            params.append(data[f])
    for f in ('products', 'solutions', 'cases', 'keywords', 'synonyms', 'related_industries'):
        v = _arr(f)
        if v is not None:
            updates.append(f'{f}=?')
            params.append(v)
    if 'enabled' in data:
        updates.append('enabled=?')
        params.append(data['enabled'])
    if updates:
        updates.append('updated_at=CURRENT_TIMESTAMP')
        params.append(cid)
        db.execute(f"UPDATE capabilities SET {', '.join(updates)} WHERE id=?", params)
        db.commit()
        record_operation_log(request.current_user, 'update', 'capability', f'编辑能力#{cid}')
    return jsonify({'code': 200, 'message': '已保存'})


@capabilities_bp.route('/<int:cid>', methods=['DELETE'])
@admin_required
def delete_capability(cid):
    db = get_db()
    row = db.execute("SELECT name FROM capabilities WHERE id=?", (cid,)).fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '能力不存在'})
    db.execute("DELETE FROM capabilities WHERE id=?", (cid,))
    db.commit()
    record_operation_log(request.current_user, 'delete', 'capability', f'删除能力:{row["name"]}')
    return jsonify({'code': 200, 'message': '已删除'})


@capabilities_bp.route('/match', methods=['POST'])
@token_required
def match_capabilities():
    """能力匹配：给定项目需求文本，匹配我方能力。

    Body: {"text": "项目需求描述", "title": "项目名称（可选）"}
    """
    from capability_matcher import match_project_capabilities
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    title = (data.get('title') or '').strip()
    if not text and not title:
        return jsonify({'code': 400, 'message': '缺少项目需求文本'})

    db = get_db()
    result = match_project_capabilities(title, text, db)
    return jsonify({'code': 200, 'data': result})
