"""AI 分析模块：客户画像 + 竞争对手分析 + 销售提醒。

Phase8: 从 intelligence_leads 聚合数据，构建客户画像和竞争对手画像，
生成销售提醒（新商机/截止临近/竞争对手中标）。
"""
import json
import re
import sqlite3
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


def _parse_budget(budget_str):
    """从预算字符串提取金额（万元）。"""
    if not budget_str:
        return 0
    # 匹配 "100万元" "100万" "1000000元"
    m = re.search(r'([\d.]+)\s*万', budget_str)
    if m:
        return float(m.group(1))
    m = re.search(r'([\d.]+)\s*元', budget_str)
    if m:
        return float(m.group(1)) / 10000
    m = re.search(r'([\d.]+)', budget_str)
    if m:
        val = float(m.group(1))
        return val if val < 100000 else val / 10000
    return 0


def build_customer_profiles(db=None):
    """从 intelligence_leads 聚合构建客户画像。

    对每个采购单位（buyer）：
    - 统计采购次数、总预算、平均预算
    - 收集采购方式、竞争对手、项目类型
    - 计算平均评分、最高评分
    - 构建采购时间线
    """
    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        db.row_factory = sqlite3.Row
        own_conn = True

    try:
        # 获取所有有 buyer 的商机
        rows = db.execute("""
            SELECT buyer, region, budget, procurement_method, project_type,
                   score, deadline, title, created_at, competitors,
                   analysis_summary, status
            FROM intelligence_leads WHERE buyer != '' AND buyer IS NOT NULL
            ORDER BY buyer, created_at
        """).fetchall()

        # 按 buyer 分组聚合
        profiles = {}
        for r in rows:
            buyer = r['buyer'].strip()
            if not buyer:
                continue
            if buyer not in profiles:
                profiles[buyer] = {
                    'buyer': buyer,
                    'region': r['region'] or '',
                    'total_procurements': 0,
                    'total_budget': 0,
                    'budgets': [],
                    'methods': set(),
                    'competitors': set(),
                    'project_types': set(),
                    'scores': [],
                    'max_score': 0,
                    'timeline': [],
                    'latest_date': '',
                }
            p = profiles[buyer]
            p['total_procurements'] += 1
            budget = _parse_budget(r['budget'])
            if budget > 0:
                p['total_budget'] += budget
                p['budgets'].append(budget)
            if r['procurement_method']:
                p['methods'].add(r['procurement_method'])
            if r['project_type']:
                p['project_types'].add(r['project_type'])
            if r['score']:
                p['scores'].append(r['score'])
                p['max_score'] = max(p['max_score'], r['score'])
            if r['competitors']:
                try:
                    comps = json.loads(r['competitors'])
                    if isinstance(comps, list):
                        for c in comps:
                            if c:
                                p['competitors'].add(c)
                except (json.JSONDecodeError, TypeError):
                    pass
            if r['region']:
                p['region'] = r['region']
            timeline_entry = {
                'title': r['title'][:50] if r['title'] else '',
                'date': r['created_at'][:10] if r['created_at'] else '',
                'deadline': r['deadline'] or '',
                'budget': r['budget'] or '',
                'score': r['score'] or 0,
                'status': r['status'] or '',
            }
            p['timeline'].append(timeline_entry)
            if r['created_at']:
                p['latest_date'] = max(p['latest_date'], r['created_at'][:10])

        # 写入数据库
        for buyer, p in profiles.items():
            avg_budget = sum(p['budgets']) / len(p['budgets']) if p['budgets'] else 0
            avg_score = sum(p['scores']) / len(p['scores']) if p['scores'] else 0

            # 判断行业
            industry = ''
            if p['project_types']:
                industry = ', '.join(list(p['project_types'])[:3])

            existing = db.execute(
                "SELECT id FROM customer_profiles WHERE buyer=?", (buyer,)
            ).fetchone()

            data = (
                buyer,
                industry,
                p['region'],
                p['total_procurements'],
                round(p['total_budget'], 2),
                round(avg_budget, 2),
                json.dumps(list(p['methods']), ensure_ascii=False),
                json.dumps(list(p['competitors']), ensure_ascii=False),
                json.dumps(list(p['project_types']), ensure_ascii=False),
                p['latest_date'],
                round(avg_score, 1),
                p['max_score'],
                json.dumps(p['timeline'][-10:], ensure_ascii=False),  # 最近10条
            )

            if existing:
                db.execute("""
                    UPDATE customer_profiles SET
                        industry=?, region=?, total_procurements=?, total_budget=?,
                        avg_budget=?, procurement_methods=?, competitors=?,
                        project_types=?, latest_date=?, avg_score=?, max_score=?,
                        timeline=?, updated_at=CURRENT_TIMESTAMP
                    WHERE buyer=?
                """, (*data[1:], buyer))
            else:
                db.execute("""
                    INSERT INTO customer_profiles (
                        buyer, industry, region, total_procurements, total_budget,
                        avg_budget, procurement_methods, competitors, project_types,
                        latest_date, avg_score, max_score, timeline
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, data)

        db.commit()
        return len(profiles)
    except Exception as e:
        logger.error(f'构建客户画像失败: {e}')
        return 0
    finally:
        if own_conn:
            db.close()


def build_competitor_profiles(db=None):
    """从 intelligence_leads 的 competitors 字段聚合构建竞争对手画像。

    对每个竞争对手：
    - 出现次数（在多少个商机中被提及）
    - 客户列表（采购单位）
    - 项目类型
    - 地区分布
    - 优势领域分析
    """
    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        db.row_factory = sqlite3.Row
        own_conn = True

    try:
        rows = db.execute("""
            SELECT buyer, competitors, project_type, region, procurement_method,
                   score, created_at
            FROM intelligence_leads WHERE competitors IS NOT NULL AND competitors != '[]'
        """).fetchall()

        profiles = {}
        for r in rows:
            try:
                comp_list = json.loads(r['competitors'])
                if not isinstance(comp_list, list):
                    continue
            except (json.JSONDecodeError, TypeError):
                continue

            for comp in comp_list:
                comp = (comp or '').strip()
                if not comp or len(comp) < 2:
                    continue
                if comp not in profiles:
                    profiles[comp] = {
                        'name': comp,
                        'appearance_count': 0,
                        'customers': set(),
                        'project_types': set(),
                        'regions': set(),
                        'methods': set(),
                        'first_seen': '',
                        'last_seen': '',
                    }
                p = profiles[comp]
                p['appearance_count'] += 1
                if r['buyer']:
                    p['customers'].add(r['buyer'])
                if r['project_type']:
                    p['project_types'].add(r['project_type'])
                if r['region']:
                    p['regions'].add(r['region'])
                if r['procurement_method']:
                    p['methods'].add(r['procurement_method'])
                date_str = r['created_at'][:10] if r['created_at'] else ''
                if date_str:
                    if not p['first_seen'] or date_str < p['first_seen']:
                        p['first_seen'] = date_str
                    if not p['last_seen'] or date_str > p['last_seen']:
                        p['last_seen'] = date_str

        # 优势领域 = 出现最多的项目类型
        for comp, p in profiles.items():
            advantage = list(p['project_types'])[:3] if p['project_types'] else []
            existing = db.execute(
                "SELECT id FROM competitor_profiles WHERE name=?", (comp,)
            ).fetchone()

            data = (
                p['appearance_count'],
                json.dumps(list(p['customers']), ensure_ascii=False),
                json.dumps(list(p['project_types']), ensure_ascii=False),
                json.dumps(list(p['regions']), ensure_ascii=False),
                json.dumps(advantage, ensure_ascii=False),
                0,  # win_count - 需要中标公告数据
                p['first_seen'],
                p['last_seen'],
            )

            if existing:
                db.execute("""
                    UPDATE competitor_profiles SET
                        appearance_count=?, customer_list=?, project_types=?,
                        regions=?, advantage_areas=?, first_seen=?, last_seen=?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE name=?
                """, (*data, comp))
            else:
                db.execute("""
                    INSERT INTO competitor_profiles (
                        name, appearance_count, customer_list, project_types,
                        regions, advantage_areas, win_count, first_seen, last_seen
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (comp, *data))

        db.commit()
        return len(profiles)
    except Exception as e:
        logger.error(f'构建竞争对手画像失败: {e}')
        return 0
    finally:
        if own_conn:
            db.close()


def generate_sales_alerts(db=None):
    """生成销售提醒。

    规则：
    1. 新高价值商机（score >= 60 且未提醒）
    2. 截止日期临近（7天内且未提醒）
    3. 竞争对手在相关商机中出现（未提醒）
    """
    own_conn = False
    if db is None:
        from extensions import DB_PATH
        db = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        db.row_factory = sqlite3.Row
        own_conn = True

    try:
        today = date.today()
        alerts_created = 0

        # 1. 高价值商机提醒（排除已作废）
        high_value = db.execute("""
            SELECT id, title, buyer, score, budget, deadline
            FROM intelligence_leads
            WHERE score >= 60 AND status NOT IN ('converted', 'rejected')
        """).fetchall()

        for r in high_value:
            # 检查是否已提醒
            existing = db.execute(
                "SELECT id FROM sales_alerts WHERE alert_type='high_value' AND related_id=? AND related_type='intelligence_lead'",
                (r['id'],)
            ).fetchone()
            if existing:
                continue

            db.execute("""
                INSERT INTO sales_alerts (alert_type, title, detail, priority, related_id, related_type)
                VALUES ('high_value', ?, ?, 'high', ?, 'intelligence_lead')
            """, (
                f'高价值商机: {r["title"][:40]}',
                f'评分:{r["score"]} 采购:{r["buyer"]} 预算:{r["budget"] or ""} 截止:{r["deadline"] or ""}',
                r['id']
            ))
            alerts_created += 1

        # 2. 截止日期临近提醒（排除已作废）
        upcoming = db.execute("""
            SELECT id, title, buyer, deadline, score
            FROM intelligence_leads
            WHERE deadline != '' AND deadline IS NOT NULL AND status NOT IN ('converted', 'rejected')
        """).fetchall()

        for r in upcoming:
            try:
                dl = date.fromisoformat(r['deadline'][:10])
                days_left = (dl - today).days
                if 0 <= days_left <= 7:
                    existing = db.execute(
                        "SELECT id FROM sales_alerts WHERE alert_type='deadline' AND related_id=?",
                        (r['id'],)
                    ).fetchone()
                    if existing:
                        continue

                    db.execute("""
                        INSERT INTO sales_alerts (alert_type, title, detail, priority, related_id, related_type)
                        VALUES ('deadline', ?, ?, 'urgent', ?, 'intelligence_lead')
                    """, (
                        f'截止临近({days_left}天): {r["title"][:40]}',
                        f'采购:{r["buyer"]} 截止:{r["deadline"]} 评分:{r["score"]}',
                        r['id']
                    ))
                    alerts_created += 1
            except (ValueError, TypeError):
                pass

        # 3. 转入CRM未分配提醒（数量归零时自动过期旧提醒，避免显示过时内容）
        unassigned = db.execute("""
            SELECT COUNT(*) as c FROM scraped_leads
            WHERE source='AI商机识别' AND status='evaluated' AND assigned_to IS NULL
        """).fetchone()['c']

        if unassigned > 0:
            existing = db.execute(
                "SELECT id FROM sales_alerts WHERE alert_type='unassigned' AND status='unread' AND DATE(created_at)=?",
                (today.isoformat(),)
            ).fetchone()
            if not existing:
                db.execute("""
                    INSERT INTO sales_alerts (alert_type, title, detail, priority)
                    VALUES ('unassigned', ?, ?, 'normal')
                """, (
                    f'{unassigned}条AI线索待分配',
                    f'CRM线索库中有{unassigned}条AI来源线索尚未分配给销售',
                ))
                alerts_created += 1
        else:
            # 已无待分配线索：过期未读的待分配提醒，并清理过期的历史待分配提醒
            db.execute("""
                UPDATE sales_alerts SET status='read', read_at=?
                WHERE alert_type='unassigned' AND status='unread'
            """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))
            db.execute("DELETE FROM sales_alerts WHERE alert_type='unassigned'")

        db.commit()
        return alerts_created
    except Exception as e:
        logger.error(f'生成销售提醒失败: {e}')
        return 0
    finally:
        if own_conn:
            db.close()


def run_full_analysis(db=None):
    """一键执行全部分析：客户画像 + 竞争对手 + 销售提醒。"""
    customers = build_customer_profiles(db)
    competitors = build_competitor_profiles(db)
    alerts = generate_sales_alerts(db)
    return {
        'customer_profiles': customers,
        'competitor_profiles': competitors,
        'sales_alerts': alerts,
    }
