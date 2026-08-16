from flask import request, jsonify
from extensions import get_db, record_operation_log, token_required
from datetime import datetime
import json

from . import marketing_bp

# 活动状态：draft(草稿) → planned(已计划) → running(进行中) → completed(已完成)/cancelled(已取消)
# running → paused(已暂停) → running
VALID_STATUSES = ('draft', 'planned', 'running', 'paused', 'completed', 'cancelled')
TERMINAL_STATUSES = ('completed', 'cancelled')

# 指标类型
VALID_METRICS = ('impressions', 'clicks', 'leads', 'conversions', 'revenue', 'cost')

# 触达状态
VALID_REACH_STATUS = ('pending', 'reached', 'interested', 'converted', 'lost')

# 自动化触发类型
VALID_TRIGGERS = ('new_lead', 'customer_tag', 'stage_change', 'schedule', 'campaign_start', 'campaign_end')
# 自动化动作类型
VALID_ACTIONS = ('email', 'sms', 'wechat', 'create_task', 'create_lead', 'assign_owner', 'add_tag')


# ==================== 营销活动 CRUD ====================

@marketing_bp.route('/api/campaigns', methods=['GET'])
@token_required
def get_campaigns():
    """营销活动列表：支持关键字、类型、状态、渠道筛选。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    keyword = request.args.get('keyword', '')
    campaign_type = request.args.get('type', '')
    status = request.args.get('status', '')
    channel = request.args.get('channel', '')

    db = get_db()
    cursor = db.cursor()

    conditions = []
    params = []

    # 普通销售仅可见自己负责的活动；管理层可见全部
    if role not in ('主任', '院长'):
        conditions.append("c.owner_id = ?")
        params.append(username)

    if keyword:
        conditions.append("(c.name LIKE ? OR c.goal LIKE ? OR c.target_audience LIKE ?)")
        params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
    if campaign_type:
        conditions.append("c.type = ?")
        params.append(campaign_type)
    if status:
        conditions.append("c.status = ?")
        params.append(status)
    if channel:
        conditions.append("c.channel = ?")
        params.append(channel)

    where_clause = ' AND '.join(conditions) if conditions else '1=1'

    cursor.execute(f"""
        SELECT c.*, u.name as owner_name, cu.name as creator_name
        FROM campaigns c
        LEFT JOIN users u ON c.owner_id = u.username
        LEFT JOIN users cu ON c.created_by = cu.username
        WHERE {where_clause}
        ORDER BY c.updated_at DESC
    """, params)

    rows = cursor.fetchall()
    data = [dict(r) for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@marketing_bp.route('/api/campaigns/<int:campaign_id>', methods=['GET'])
@token_required
def get_campaign_detail(campaign_id):
    """营销活动详情：含主表 + 汇总指标 + 受众统计。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    if role in ('主任', '院长'):
        cursor.execute("""
            SELECT c.*, u.name as owner_name, cu.name as creator_name
            FROM campaigns c
            LEFT JOIN users u ON c.owner_id = u.username
            LEFT JOIN users cu ON c.created_by = cu.username
            WHERE c.id = ?
        """, (campaign_id,))
    else:
        cursor.execute("""
            SELECT c.*, u.name as owner_name, cu.name as creator_name
            FROM campaigns c
            LEFT JOIN users u ON c.owner_id = u.username
            LEFT JOIN users cu ON c.created_by = cu.username
            WHERE c.id = ? AND c.owner_id = ?
        """, (campaign_id, username))

    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '营销活动不存在', 'data': None})

    campaign = dict(row)

    # 指标记录列表（按时间倒序）
    cursor.execute("""
        SELECT m.*, u.name as recorder_name
        FROM campaign_metrics m
        LEFT JOIN users u ON m.recorded_by = u.username
        WHERE m.campaign_id = ?
        ORDER BY m.recorded_at DESC
    """, (campaign_id,))
    campaign['metrics'] = [dict(r) for r in cursor.fetchall()]

    # 受众触达统计
    cursor.execute("""
        SELECT reach_status, COUNT(*) as cnt
        FROM campaign_audiences
        WHERE campaign_id = ?
        GROUP BY reach_status
    """, (campaign_id,))
    campaign['audience_stats'] = [dict(r) for r in cursor.fetchall()]

    return jsonify({'code': 200, 'message': 'success', 'data': campaign})


@marketing_bp.route('/api/campaigns', methods=['POST'])
@token_required
def create_campaign():
    """创建营销活动。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    if not data.get('name'):
        return jsonify({'code': 400, 'message': '活动名称不能为空', 'data': None})

    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("""
            INSERT INTO campaigns (name, type, channel, budget, actual_cost, start_date, end_date,
                status, target_audience, goal, owner_id, created_by, created_at, updated_at, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        """, (
            data.get('name'), data.get('type'), data.get('channel'),
            data.get('budget') or 0, data.get('actual_cost') or 0,
            data.get('start_date'), data.get('end_date'),
            data.get('status') or 'draft', data.get('target_audience'), data.get('goal'),
            data.get('owner_id') or username, username, data.get('remark') or ''
        ))
        campaign_id = cursor.lastrowid
        db.commit()
        record_operation_log(username, '创建', '营销活动', f'创建营销活动：{data.get("name")}')
        return jsonify({'code': 200, 'message': '营销活动创建成功', 'data': {'id': campaign_id}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/<int:campaign_id>', methods=['PUT'])
@token_required
def update_campaign(campaign_id):
    """编辑营销活动。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name, status FROM campaigns WHERE id=?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '营销活动不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能编辑自己的活动', 'data': None})

    # 终态状态不允许编辑
    if row['status'] in TERMINAL_STATUSES:
        return jsonify({'code': 400, 'message': f'活动当前状态为 {row["status"]}，不可编辑', 'data': None})

    can_change_owner = role in ('主任', '院长')
    try:
        if can_change_owner and 'owner_id' in data:
            cursor.execute("""
                UPDATE campaigns SET
                    name=?, type=?, channel=?, budget=?, actual_cost=?, start_date=?, end_date=?,
                    target_audience=?, goal=?, owner_id=?, remark=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('name'), data.get('type'), data.get('channel'),
                data.get('budget') or 0, data.get('actual_cost') or 0,
                data.get('start_date'), data.get('end_date'),
                data.get('target_audience'), data.get('goal'),
                data.get('owner_id'), data.get('remark') or '', campaign_id
            ))
        else:
            cursor.execute("""
                UPDATE campaigns SET
                    name=?, type=?, channel=?, budget=?, actual_cost=?, start_date=?, end_date=?,
                    target_audience=?, goal=?, remark=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (
                data.get('name'), data.get('type'), data.get('channel'),
                data.get('budget') or 0, data.get('actual_cost') or 0,
                data.get('start_date'), data.get('end_date'),
                data.get('target_audience'), data.get('goal'),
                data.get('remark') or '', campaign_id
            ))
        db.commit()
        record_operation_log(username, '编辑', '营销活动', f'编辑营销活动：{data.get("name") or row["name"]}')
        return jsonify({'code': 200, 'message': '营销活动更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
@token_required
def delete_campaign(campaign_id):
    """删除营销活动（级联删除指标、受众记录）。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name FROM campaigns WHERE id=?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '营销活动不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足，只能删除自己的活动', 'data': None})

    try:
        cursor.execute("DELETE FROM campaign_metrics WHERE campaign_id=?", (campaign_id,))
        cursor.execute("DELETE FROM campaign_audiences WHERE campaign_id=?", (campaign_id,))
        cursor.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))
        db.commit()
        record_operation_log(username, '删除', '营销活动', f'删除营销活动：{row["name"]}（ID:{campaign_id}）')
        return jsonify({'code': 200, 'message': '营销活动删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/<int:campaign_id>/status', methods=['POST'])
@token_required
def update_campaign_status(campaign_id):
    """更新营销活动状态：draft→planned→running→completed/cancelled；running↔paused"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name, status FROM campaigns WHERE id=?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '营销活动不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    new_status = (data.get('status') or '').lower()
    if new_status not in VALID_STATUSES:
        return jsonify({'code': 400, 'message': f'status 必须为 {VALID_STATUSES} 之一', 'data': None})

    old_status = row['status']
    # 终态状态不允许变更
    if old_status in TERMINAL_STATUSES:
        return jsonify({'code': 400, 'message': f'活动已 {old_status}，不可再变更状态', 'data': None})

    try:
        cursor.execute("UPDATE campaigns SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (new_status, campaign_id))
        db.commit()
        record_operation_log(username, '状态变更', '营销活动',
            f'{row["name"]}：{old_status} → {new_status}')
        return jsonify({'code': 200, 'message': '状态更新成功', 'data': {'status': new_status}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 营销效果指标 ====================

@marketing_bp.route('/api/campaigns/<int:campaign_id>/metrics', methods=['GET'])
@token_required
def get_campaign_metrics(campaign_id):
    """获取营销活动的效果指标记录。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id FROM campaigns WHERE id=?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '营销活动不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    metric_type = request.args.get('metric_type', '')

    if metric_type:
        cursor.execute("""
            SELECT m.*, u.name as recorder_name
            FROM campaign_metrics m
            LEFT JOIN users u ON m.recorded_by = u.username
            WHERE m.campaign_id = ? AND m.metric_type = ?
            ORDER BY m.recorded_at DESC
        """, (campaign_id, metric_type))
    else:
        cursor.execute("""
            SELECT m.*, u.name as recorder_name
            FROM campaign_metrics m
            LEFT JOIN users u ON m.recorded_by = u.username
            WHERE m.campaign_id = ?
            ORDER BY m.recorded_at DESC
        """, (campaign_id,))

    rows = cursor.fetchall()
    data = [dict(r) for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@marketing_bp.route('/api/campaigns/<int:campaign_id>/metrics', methods=['POST'])
@token_required
def record_campaign_metric(campaign_id):
    """录入营销效果指标。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name FROM campaigns WHERE id=?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '营销活动不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    metric_type = (data.get('metric_type') or '').lower()
    if metric_type not in VALID_METRICS:
        return jsonify({'code': 400, 'message': f'metric_type 必须为 {VALID_METRICS} 之一', 'data': None})

    try:
        metric_value = float(data.get('metric_value') or 0)
    except (TypeError, ValueError):
        return jsonify({'code': 400, 'message': 'metric_value 必须为数字', 'data': None})

    # 如果是 cost 类型，同步更新活动的 actual_cost
    try:
        cursor.execute("""
            INSERT INTO campaign_metrics (campaign_id, metric_type, metric_value, recorded_at, recorded_by, remark)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
        """, (campaign_id, metric_type, metric_value, username, data.get('remark') or ''))

        if metric_type == 'cost':
            cursor.execute("UPDATE campaigns SET actual_cost=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (metric_value, campaign_id))

        db.commit()
        record_operation_log(username, '录入指标', '营销活动',
            f'{row["name"]} - {metric_type}: {metric_value}')
        return jsonify({'code': 200, 'message': '指标录入成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/metrics/<int:metric_id>', methods=['DELETE'])
@token_required
def delete_campaign_metric(metric_id):
    """删除营销效果指标记录。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT m.id, m.campaign_id, m.metric_type, m.recorded_by, c.owner_id
        FROM campaign_metrics m
        JOIN campaigns c ON m.campaign_id = c.id
        WHERE m.id = ?
    """, (metric_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '指标记录不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username and row['recorded_by'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    try:
        cursor.execute("DELETE FROM campaign_metrics WHERE id=?", (metric_id,))
        db.commit()
        return jsonify({'code': 200, 'message': '指标记录删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 营销效果分析 ====================

@marketing_bp.route('/api/campaigns/analytics', methods=['GET'])
@token_required
def get_campaign_analytics():
    """营销效果分析：按活动汇总各指标，计算 ROI、转化率等。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    owner_filter = "" if role in ('主任', '院长') else "AND c.owner_id = ?"
    owner_params = [] if role in ('主任', '院长') else [username]

    # 取每个活动各指标的累计值
    cursor.execute(f"""
        SELECT c.id, c.name, c.type, c.channel, c.status, c.budget, c.actual_cost,
               c.start_date, c.end_date, u.name as owner_name,
               m.metric_type, SUM(m.metric_value) as total
        FROM campaigns c
        LEFT JOIN campaign_metrics m ON c.id = m.campaign_id
        LEFT JOIN users u ON c.owner_id = u.username
        WHERE 1=1 {owner_filter}
        GROUP BY c.id, m.metric_type
        ORDER BY c.id
    """, owner_params)

    rows = cursor.fetchall()

    # 按活动聚合指标
    campaigns_map = {}
    for r in rows:
        cid = r['id']
        if cid not in campaigns_map:
            campaigns_map[cid] = {
                'id': cid,
                'name': r['name'],
                'type': r['type'],
                'channel': r['channel'],
                'status': r['status'],
                'budget': float(r['budget'] or 0),
                'actual_cost': float(r['actual_cost'] or 0),
                'start_date': r['start_date'],
                'end_date': r['end_date'],
                'owner_name': r['owner_name'],
                'impressions': 0, 'clicks': 0, 'leads': 0,
                'conversions': 0, 'revenue': 0, 'cost': 0
            }
        if r['metric_type']:
            campaigns_map[cid][r['metric_type']] = float(r['total'] or 0)

    # 计算衍生指标：点击率、转化率、ROI
    for c in campaigns_map.values():
        c['ctr'] = round(c['clicks'] / c['impressions'] * 100, 2) if c['impressions'] > 0 else 0
        c['conversion_rate'] = round(c['conversions'] / c['leads'] * 100, 2) if c['leads'] > 0 else 0
        c['roi'] = round((c['revenue'] - c['actual_cost']) / c['actual_cost'] * 100, 2) if c['actual_cost'] > 0 else 0

    # 汇总统计
    summary = {
        'total_campaigns': len(campaigns_map),
        'total_budget': round(sum(c['budget'] for c in campaigns_map.values()), 2),
        'total_cost': round(sum(c['actual_cost'] for c in campaigns_map.values()), 2),
        'total_revenue': round(sum(c['revenue'] for c in campaigns_map.values()), 2),
        'total_impressions': sum(c['impressions'] for c in campaigns_map.values()),
        'total_clicks': sum(c['clicks'] for c in campaigns_map.values()),
        'total_leads': sum(c['leads'] for c in campaigns_map.values()),
        'total_conversions': sum(c['conversions'] for c in campaigns_map.values()),
    }

    return jsonify({
        'code': 200,
        'message': 'success',
        'data': {
            'campaigns': list(campaigns_map.values()),
            'summary': summary
        }
    })


# ==================== 营销触达受众 ====================

@marketing_bp.route('/api/campaigns/<int:campaign_id>/audiences', methods=['GET'])
@token_required
def get_campaign_audiences(campaign_id):
    """获取营销活动触达受众列表。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id FROM campaigns WHERE id=?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '营销活动不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    reach_status = request.args.get('reach_status', '')

    if reach_status:
        cursor.execute("""
            SELECT a.*, c.company as customer_name, c.name as customer_contact
            FROM campaign_audiences a
            LEFT JOIN customers c ON a.cust_id = c.id
            WHERE a.campaign_id = ? AND a.reach_status = ?
            ORDER BY a.created_at DESC
        """, (campaign_id, reach_status))
    else:
        cursor.execute("""
            SELECT a.*, c.company as customer_name, c.name as customer_contact
            FROM campaign_audiences a
            LEFT JOIN customers c ON a.cust_id = c.id
            WHERE a.campaign_id = ?
            ORDER BY a.created_at DESC
        """, (campaign_id,))

    rows = cursor.fetchall()
    data = [dict(r) for r in rows]
    return jsonify({'code': 200, 'message': 'success', 'data': data})


@marketing_bp.route('/api/campaigns/<int:campaign_id>/audiences', methods=['POST'])
@token_required
def add_campaign_audience(campaign_id):
    """添加营销活动触达受众（支持批量）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name FROM campaigns WHERE id=?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '营销活动不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    # 支持批量添加：audiences 数组 或 单个 audience
    audiences = data.get('audiences')
    if not audiences:
        audiences = [data]

    added = 0
    try:
        for aud in audiences:
            if not aud.get('cust_id') and not aud.get('contact_name'):
                continue
            cursor.execute("""
                INSERT INTO campaign_audiences (campaign_id, cust_id, contact_name, contact_info,
                    reach_status, feedback, reached_at, converted_amount, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                campaign_id, aud.get('cust_id'), aud.get('contact_name'), aud.get('contact_info'),
                aud.get('reach_status') or 'pending', aud.get('feedback') or '',
                aud.get('reached_at'), aud.get('converted_amount') or 0
            ))
            added += 1

        db.commit()
        record_operation_log(username, '添加受众', '营销活动',
            f'{row["name"]} 添加 {added} 个受众')
        return jsonify({'code': 200, 'message': f'成功添加 {added} 个受众', 'data': {'added': added}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/audiences/<int:aud_id>', methods=['PUT'])
@token_required
def update_campaign_audience(aud_id):
    """更新受众触达状态（支持记录反馈、转化金额）。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.id, a.campaign_id, a.reach_status, c.owner_id
        FROM campaign_audiences a
        JOIN campaigns c ON a.campaign_id = c.id
        WHERE a.id = ?
    """, (aud_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '受众记录不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    reach_status = (data.get('reach_status') or '').lower()
    if reach_status and reach_status not in VALID_REACH_STATUS:
        return jsonify({'code': 400, 'message': f'reach_status 必须为 {VALID_REACH_STATUS} 之一', 'data': None})

    try:
        reached_at = data.get('reached_at')
        if reach_status in ('reached', 'interested', 'converted') and not reached_at:
            reached_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute("""
            UPDATE campaign_audiences SET
                reach_status=COALESCE(?, reach_status),
                feedback=COALESCE(?, feedback),
                reached_at=COALESCE(?, reached_at),
                converted_amount=COALESCE(?, converted_amount)
            WHERE id=?
        """, (reach_status or None, data.get('feedback'), reached_at,
              data.get('converted_amount'), aud_id))
        db.commit()
        return jsonify({'code': 200, 'message': '受众状态更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/audiences/<int:aud_id>', methods=['DELETE'])
@token_required
def delete_campaign_audience(aud_id):
    """删除营销触达受众记录。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        SELECT a.id, c.owner_id, c.name
        FROM campaign_audiences a
        JOIN campaigns c ON a.campaign_id = c.id
        WHERE a.id = ?
    """, (aud_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '受众记录不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    try:
        cursor.execute("DELETE FROM campaign_audiences WHERE id=?", (aud_id,))
        db.commit()
        return jsonify({'code': 200, 'message': '受众记录删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


# ==================== 营销自动化规则 ====================

@marketing_bp.route('/api/campaigns/automations', methods=['GET'])
@token_required
def get_automations():
    """营销自动化规则列表。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    owner_filter = "" if role in ('主任', '院长') else "AND a.owner_id = ?"
    owner_params = [] if role in ('主任', '院长') else [username]

    cursor.execute(f"""
        SELECT a.*, u.name as owner_name
        FROM campaign_automations a
        LEFT JOIN users u ON a.owner_id = u.username
        WHERE 1=1 {owner_filter}
        ORDER BY a.updated_at DESC
    """, owner_params)

    rows = cursor.fetchall()
    data = []
    for r in rows:
        item = dict(r)
        # 解析 JSON 配置
        try:
            item['trigger_config'] = json.loads(item['trigger_config']) if item['trigger_config'] else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        try:
            item['action_config'] = json.loads(item['action_config']) if item['action_config'] else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        data.append(item)

    return jsonify({'code': 200, 'message': 'success', 'data': data})


@marketing_bp.route('/api/campaigns/automations', methods=['POST'])
@token_required
def create_automation():
    """创建营销自动化规则。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']

    if not data.get('name'):
        return jsonify({'code': 400, 'message': '规则名称不能为空', 'data': None})

    trigger_type = (data.get('trigger_type') or '').lower()
    if trigger_type and trigger_type not in VALID_TRIGGERS:
        return jsonify({'code': 400, 'message': f'trigger_type 必须为 {VALID_TRIGGERS} 之一', 'data': None})

    action_type = (data.get('action_type') or '').lower()
    if action_type and action_type not in VALID_ACTIONS:
        return jsonify({'code': 400, 'message': f'action_type 必须为 {VALID_ACTIONS} 之一', 'data': None})

    db = get_db()
    cursor = db.cursor()

    # trigger_config / action_config 存为 JSON 字符串
    trigger_config = data.get('trigger_config')
    if isinstance(trigger_config, (dict, list)):
        trigger_config = json.dumps(trigger_config, ensure_ascii=False)
    action_config = data.get('action_config')
    if isinstance(action_config, (dict, list)):
        action_config = json.dumps(action_config, ensure_ascii=False)

    try:
        cursor.execute("""
            INSERT INTO campaign_automations (name, trigger_type, trigger_config, action_type, action_config,
                status, owner_id, created_at, updated_at, remark)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
        """, (
            data.get('name'), trigger_type, trigger_config, action_type, action_config,
            data.get('status') or 'active', data.get('owner_id') or username, data.get('remark') or ''
        ))
        auto_id = cursor.lastrowid
        db.commit()
        record_operation_log(username, '创建', '营销自动化', f'创建自动化规则：{data.get("name")}')
        return jsonify({'code': 200, 'message': '自动化规则创建成功', 'data': {'id': auto_id}})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/automations/<int:auto_id>', methods=['PUT'])
@token_required
def update_automation(auto_id):
    """编辑营销自动化规则。"""
    payload = request.current_user
    data = request.get_json(silent=True) or {}
    username = payload['username']
    role = payload['role']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name FROM campaign_automations WHERE id=?", (auto_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '自动化规则不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    trigger_type = (data.get('trigger_type') or '').lower()
    if trigger_type and trigger_type not in VALID_TRIGGERS:
        return jsonify({'code': 400, 'message': f'trigger_type 必须为 {VALID_TRIGGERS} 之一', 'data': None})

    action_type = (data.get('action_type') or '').lower()
    if action_type and action_type not in VALID_ACTIONS:
        return jsonify({'code': 400, 'message': f'action_type 必须为 {VALID_ACTIONS} 之一', 'data': None})

    trigger_config = data.get('trigger_config')
    if isinstance(trigger_config, (dict, list)):
        trigger_config = json.dumps(trigger_config, ensure_ascii=False)
    action_config = data.get('action_config')
    if isinstance(action_config, (dict, list)):
        action_config = json.dumps(action_config, ensure_ascii=False)

    try:
        cursor.execute("""
            UPDATE campaign_automations SET
                name=COALESCE(?, name),
                trigger_type=COALESCE(?, trigger_type),
                trigger_config=COALESCE(?, trigger_config),
                action_type=COALESCE(?, action_type),
                action_config=COALESCE(?, action_config),
                status=COALESCE(?, status),
                owner_id=COALESCE(?, owner_id),
                remark=COALESCE(?, remark),
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (
            data.get('name'), trigger_type or None, trigger_config,
            action_type or None, action_config,
            data.get('status'), data.get('owner_id'), data.get('remark'), auto_id
        ))
        db.commit()
        record_operation_log(username, '编辑', '营销自动化', f'编辑自动化规则：{data.get("name") or row["name"]}')
        return jsonify({'code': 200, 'message': '自动化规则更新成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/automations/<int:auto_id>', methods=['DELETE'])
@token_required
def delete_automation(auto_id):
    """删除营销自动化规则。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name FROM campaign_automations WHERE id=?", (auto_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '自动化规则不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    try:
        cursor.execute("DELETE FROM campaign_automations WHERE id=?", (auto_id,))
        db.commit()
        record_operation_log(username, '删除', '营销自动化', f'删除自动化规则：{row["name"]}（ID:{auto_id}）')
        return jsonify({'code': 200, 'message': '自动化规则删除成功', 'data': None})
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


@marketing_bp.route('/api/campaigns/automations/<int:auto_id>/run', methods=['POST'])
@token_required
def run_automation(auto_id):
    """手动执行营销自动化规则。"""
    payload = request.current_user
    role = payload['role']
    username = payload['username']

    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT owner_id, name, status, trigger_type, action_type FROM campaign_automations WHERE id=?", (auto_id,))
    row = cursor.fetchone()
    if not row:
        return jsonify({'code': 404, 'message': '自动化规则不存在', 'data': None})
    if role not in ('主任', '院长') and row['owner_id'] != username:
        return jsonify({'code': 403, 'message': '权限不足', 'data': None})

    if row['status'] != 'active':
        return jsonify({'code': 400, 'message': '规则未启用，无法执行', 'data': None})

    try:
        cursor.execute("""
            UPDATE campaign_automations
            SET run_count = run_count + 1, last_run_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (auto_id,))
        db.commit()
        record_operation_log(username, '执行', '营销自动化',
            f'手动执行规则：{row["name"]}（触发:{row["trigger_type"]}→动作:{row["action_type"]}）')
        return jsonify({
            'code': 200,
            'message': '自动化规则执行成功',
            'data': {
                'name': row['name'],
                'trigger_type': row['trigger_type'],
                'action_type': row['action_type']
            }
        })
    except Exception as e:
        db.rollback()
        return jsonify({'code': 500, 'message': str(e), 'data': None})


def register_routes(app):
    app.register_blueprint(marketing_bp)
