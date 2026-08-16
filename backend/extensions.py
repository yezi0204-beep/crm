from flask import Flask, g, request, jsonify
from functools import wraps
import sqlite3
import bcrypt
import os
import uuid
import time
import threading
from datetime import datetime, timedelta
from collections import defaultdict

SECRET_KEY = os.environ.get('SECRET_KEY', "crm_secret_key_2026")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, "crm_app.db"))
UPLOAD_DIR = os.environ.get('UPLOAD_DIR', os.path.join(BASE_DIR, "uploads", "contracts"))

LOGIN_ATTEMPTS = defaultdict(list)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300

ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://localhost:3000',
    'http://127.0.0.1:5173',
]
_extra_origins = os.environ.get('CORS_ALLOWED_ORIGINS', '')
if _extra_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in _extra_origins.split(',') if o.strip()])


def get_db():
    """获取请求级数据库连接。

    注意：不再在此调用 _init_tables()。建表工作由 ensure_tables() 在应用启动时
    一次性完成。若每次请求都执行 DDL（CREATE TABLE / ALTER TABLE），会长时间
    持有写锁，导致并发请求（如登录）因等待锁而超时——这正是"数据库被锁、登录不上"
    的根本原因。
    """
    if 'db' not in g:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
        g.db = conn
    return g.db


def close_db(error=None):
    if hasattr(g, 'db'):
        try:
            g.db.close()
        except Exception:
            pass


def ensure_tables():
    """应用启动时预建所有表（请求上下文外，供调度器等提前使用）。

    只在启动时执行一次所有 DDL，避免每次请求重复建表导致锁竞争。
    """
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
        _init_tables(conn)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ensure_tables] 初始化表失败: {e}")


def _init_tables(db):
    cursor = db.cursor()
    _init_users_table(cursor)
    _init_tokens_table(cursor)
    _init_business_table(cursor)
    _init_contracts_table(cursor)
    _init_operation_logs_table(cursor)
    _init_visits_table(cursor)
    _init_user_roles_table(cursor)
    _init_knowledge_base_table(cursor)
    _init_knowledge_extension_tables(cursor)
    _init_lead_tables(cursor)
    _init_follow_logs_table(cursor)
    _init_enterprise_table(cursor)
    _init_other_tables(cursor)
    db.commit()


def _init_users_table(cursor):
    """初始化用户表，确保包含 id、username、password_hash 等必要字段。"""
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL DEFAULT '',
                password_hash TEXT,
                name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '员工',
                status TEXT DEFAULT '在职',
                department TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass
    # 为已有 users 表补齐缺失字段
    for col, decl in [
        ('password', 'TEXT DEFAULT '''),
        ('password_hash', 'TEXT'),
        ('name', "TEXT NOT NULL DEFAULT ''"),
        ('role', "TEXT NOT NULL DEFAULT '员工'"),
        ('status', "TEXT DEFAULT '在职'"),
        ('department', "TEXT DEFAULT ''"),
        ('created_at', 'TEXT DEFAULT CURRENT_TIMESTAMP'),
    ]:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col} {decl}")
        except Exception:
            pass


def _init_tokens_table(cursor):
    """初始化令牌表。"""
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                expires TEXT NOT NULL
            )
        """)
    except Exception:
        pass


def _init_other_tables(cursor):
    """其他可能被引用的表，按需补建。"""
    pass


def _init_knowledge_base_table(cursor):
    """知识库表：存储 AI 拜访复盘摘要、跟进洞察、销售技巧等企业知识资产。"""
    try:
        cursor.execute("""
            CREATE TABLE knowledge_base (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT DEFAULT 'visit_summary',
                cust_id INTEGER,
                visit_id INTEGER,
                owner_id TEXT,
                tags TEXT,
                summary TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cust_id) REFERENCES customers(id),
                FOREIGN KEY (visit_id) REFERENCES visits(id)
            )
        """)
    except:
        pass


def _init_knowledge_extension_tables(cursor):
    """知识库扩展表：文档库、向量索引、资质信息、CRM关联。"""
    # 文档库：拜访纪要/合同/投标文件/技术方案等非结构化文档
    try:
        cursor.execute("""
            CREATE TABLE knowledge_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT,
                file_path TEXT,
                file_name TEXT,
                file_size INTEGER,
                mime_type TEXT,
                doc_metadata TEXT,
                cust_id INTEGER,
                business_id INTEGER,
                contract_id INTEGER,
                import_batch_id TEXT,
                owner_id TEXT,
                tags TEXT,
                summary TEXT,
                processed INTEGER DEFAULT 0,
                processed_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_doc_type ON knowledge_documents(doc_type)")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_doc_cust ON knowledge_documents(cust_id)")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_doc_business ON knowledge_documents(business_id)")
    except:
        pass

    # 向量索引：文档的语义向量存储
    try:
        cursor.execute("""
            CREATE TABLE knowledge_vectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                chunk_index INTEGER DEFAULT 0,
                chunk_text TEXT,
                vector BLOB,
                vector_dim INTEGER,
                embedding_model TEXT DEFAULT 'text-embedding-3-small',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doc_id) REFERENCES knowledge_documents(id)
            )
        """)
    except:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vectors_doc ON knowledge_vectors(doc_id)")
    except:
        pass

    # 人员资质信息
    try:
        cursor.execute("""
            CREATE TABLE personnel_qualifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                qualification_type TEXT NOT NULL,
                qualification_name TEXT,
                certificate_no TEXT,
                issue_date TEXT,
                expire_date TEXT,
                issue_authority TEXT,
                specialty TEXT,
                level TEXT,
                file_path TEXT,
                status TEXT DEFAULT '有效',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users(username)
            )
        """)
    except:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_personnel_username ON personnel_qualifications(username)")
    except:
        pass

    # 企业资质信息
    try:
        cursor.execute("""
            CREATE TABLE company_qualifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qualification_type TEXT NOT NULL,
                qualification_name TEXT,
                certificate_no TEXT,
                issue_date TEXT,
                expire_date TEXT,
                issue_authority TEXT,
                scope TEXT,
                level TEXT,
                file_path TEXT,
                status TEXT DEFAULT '有效',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except:
        pass

    # CRM数据自动同步配置
    try:
        cursor.execute("""
            CREATE TABLE crm_sync_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                last_sync_at TEXT,
                sync_interval_hours INTEGER DEFAULT 24,
                field_mapping TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(module)
            )
        """)
    except:
        pass

    # 智能推荐历史记录
    try:
        cursor.execute("""
            CREATE TABLE ai_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recommendation_type TEXT NOT NULL,
                target_id INTEGER,
                target_type TEXT,
                recommended_data TEXT,
                reason TEXT,
                score REAL,
                used INTEGER DEFAULT 0,
                used_at TEXT,
                created_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rec_type ON ai_recommendations(recommendation_type)")
    except:
        pass

    # 投标打分评估记录
    try:
        cursor.execute("""
            CREATE TABLE bid_evaluations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bid_id TEXT,
                project_name TEXT,
                evaluator TEXT,
                total_score REAL DEFAULT 0,
                score_details TEXT,
                evaluation_result TEXT,
                recommendation TEXT,
                status TEXT DEFAULT '待评估',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except:
        pass

    # 为已有表追加缺失字段
    try:
        cursor.execute("ALTER TABLE knowledge_documents ADD COLUMN summary TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE knowledge_documents ADD COLUMN import_batch_id TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE knowledge_documents ADD COLUMN analysis_result TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE knowledge_documents ADD COLUMN analysis_status TEXT DEFAULT 'pending'")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE knowledge_documents ADD COLUMN analyzed_at TEXT")
    except:
        pass


def _init_lead_tables(cursor):
    """智能线索管理：多渠道线索源配置 + 抓取线索队列。"""
    # 线索源：可配置的外部抓取渠道（RSS/API/示例/手动导入）
    try:
        cursor.execute("""
            CREATE TABLE lead_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'sample',
                url TEXT,
                config TEXT,
                keywords TEXT,
                industry TEXT,
                region TEXT,
                enabled INTEGER DEFAULT 1,
                interval_hours INTEGER DEFAULT 24,
                last_scraped_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except:
        pass
    # 抓取线索队列：经 AI 评估意向后精准分配
    try:
        cursor.execute("""
            CREATE TABLE scraped_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER,
                company TEXT,
                opportunity_name TEXT,
                contact_name TEXT,
                phone TEXT,
                email TEXT,
                industry TEXT,
                region TEXT,
                source TEXT,
                link TEXT,
                remark TEXT,
                raw_data TEXT,
                intent_score INTEGER,
                eval_reason TEXT,
                assigned_to TEXT,
                status TEXT DEFAULT 'pending',
                scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
                evaluated_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES lead_sources(id)
            )
        """)
    except:
        pass
    # 兼容已部署环境：为 scraped_leads 幂等新增 opportunity_name（商机名称）/ link（获取链接）字段
    try:
        cursor.execute("ALTER TABLE scraped_leads ADD COLUMN opportunity_name TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE scraped_leads ADD COLUMN link TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE scraped_leads ADD COLUMN category TEXT")
    except:
        pass
    # 军采监控扩展字段：发布日期/截止日期/预算金额/采购方式
    try:
        cursor.execute("ALTER TABLE scraped_leads ADD COLUMN publish_date TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE scraped_leads ADD COLUMN deadline TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE scraped_leads ADD COLUMN budget TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE scraped_leads ADD COLUMN procurement_method TEXT")
    except:
        pass
    # lead_sources 幂等新增 category（能力域：招投标监控/电商商机/企业客源/竞品情报/舆情痛点/RSS订阅）
    try:
        cursor.execute("ALTER TABLE lead_sources ADD COLUMN category TEXT")
    except:
        pass
    # 回填已有源/线索的 category（旧 RSS 源归入招投标监控）
    try:
        cursor.execute("UPDATE lead_sources SET category='招投标监控' WHERE (category IS NULL OR category='') AND source_type='rss'")
    except:
        pass
    try:
        cursor.execute("UPDATE scraped_leads SET category='招投标监控' WHERE (category IS NULL OR category='')")
    except:
        pass
    # 历史线索回填：opportunity_name 取 remark 兜底 company（link 不造假，留空）
    try:
        cursor.execute("""
            UPDATE scraped_leads
            SET opportunity_name = COALESCE(NULLIF(remark, ''), company)
            WHERE (opportunity_name IS NULL OR opportunity_name = '') AND company IS NOT NULL AND company != ''
        """)
    except:
        pass
    # 一次性迁移：移除旧的演示型 sample 源及其造假线索，替换为真实 RSS 源
    _migrate_to_real_sources(cursor)
    # 预置真实线索源（按 name 幂等插入，新增源不影响已有源配置）
    _seed_lead_sources(cursor)


def _migrate_to_real_sources(cursor):
    """一次性迁移：移除演示型 sample 源及百度搜索链接线索，改用真实 RSS 源。

    仅在检测到旧的 sample 预置源（如"卫星遥感需求"）存在时执行，执行后幂等。
    """
    try:
        cursor.execute("SELECT id FROM lead_sources WHERE name='卫星遥感需求' AND source_type='sample' LIMIT 1")
        if not cursor.fetchone():
            return  # 无旧 sample 源，跳过
        # 1. 删除 sample 源及无 URL 的 api 源的非已分配线索（已分配线索已转为客户，保留审计）
        cursor.execute("""
            DELETE FROM scraped_leads
            WHERE status != 'imported'
            AND source_id IN (
                SELECT id FROM lead_sources
                WHERE source_type='sample' OR (source_type='api' AND (url IS NULL OR url=''))
            )
        """)
        # 2. 已分配线索解除外键关联后保留
        cursor.execute("""
            UPDATE scraped_leads SET source_id=NULL
            WHERE source_id IN (
                SELECT id FROM lead_sources
                WHERE source_type='sample' OR (source_type='api' AND (url IS NULL OR url=''))
            )
        """)
        # 3. 删除旧的演示源
        cursor.execute("""
            DELETE FROM lead_sources
            WHERE source_type='sample' OR (source_type='api' AND (url IS NULL OR url=''))
        """)
    except Exception:
        pass
    # 清理含百度搜索链接的造假线索（非已分配）
    try:
        cursor.execute("DELETE FROM scraped_leads WHERE link LIKE '%baidu.com%' AND status != 'imported'")
    except Exception:
        pass
    # 已分配线索若含百度链接，清空 link（不保留造假链接）
    try:
        cursor.execute("UPDATE scraped_leads SET link=NULL WHERE link LIKE '%baidu.com%'")
    except Exception:
        pass


def _seed_lead_sources(cursor):
    """预置五大能力域真实线索源（按名称幂等插入）。

    五大能力域：
      1. 招投标监控——真实采购网 RSS（link 取自 RSS item 真实公告链接）
      2. 电商商机——电商榜单/热搜 HTML（需动态渲染，playwright 缺失时降级返回空）
      3. 企业客源——企业信用公示系统 HTML（需动态渲染）
      4. 竞品情报——用户自配竞品官网 URL（不预置，避免无目标抓取）
      5. 舆情痛点——知乎/贴吧等垂直社区 HTML（需动态渲染）

    通过 keywords 过滤本公司关注领域（卫星遥感/卫星通信/AI智能体/军工装备），
    industry 由 leads.py _detect_industry 自动分类。
    不预置任何 sample 演示源（不生成造假数据）；html 源抓取失败返回空列表，不造假。
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # 清理与新源重复的旧版预置源（同名或同 URL 不同名，避免重复抓取产生重复线索）
    try:
        cursor.execute("DELETE FROM scraped_leads WHERE source_id IN (SELECT id FROM lead_sources WHERE name='政府采购招标信息')")
        cursor.execute("DELETE FROM lead_sources WHERE name='政府采购招标信息'")
    except Exception:
        pass
    # 覆盖本公司9大业务领域的关键词（用于过滤真实采购公告）
    domain_kw = '装备健康,模拟器,雷达,卫通,智能体,仿真,软件,卫星,靶场,对抗,遥感,通信终端,军用,装备,武器'
    # (name, source_type, url, config, keywords, industry, region, enabled, interval_hours, category)
    sources = [
        # ========== 1. 招投标监控（真实采购网 RSS）==========
        ('中国政府采购网-招标公告', 'rss', 'http://www.ccgp.gov.cn/cggg/zygg/gkzb/rss.xml',
         '{"max_items": 30}', domain_kw, '信息技术', '全国', 1, 12, '招投标监控'),
        ('中国政府采购网-中标公告', 'rss', 'http://www.ccgp.gov.cn/cggg/zygg/zbgg/rss.xml',
         '{"max_items": 30}', domain_kw, '信息技术', '全国', 1, 12, '招投标监控'),
        ('全军武器装备采购信息网', 'rss', 'http://www.plap.cn/',
         '{"max_items": 30}', '装备,武器,军用,军采,国防,采购', '军工装备', '全国', 1, 12, '招投标监控'),
        ('全国公共资源交易平台', 'rss', 'https://www.ggzy.gov.cn/',
         '{"max_items": 30}', domain_kw, '信息技术', '全国', 1, 12, '招投标监控'),
        ('中国招标投标公共服务平台', 'rss', 'http://bulletin.cebpubservice.com/',
         '{"max_items": 30}', domain_kw, '信息技术', '全国', 1, 12, '招投标监控'),
        # ========== 2. 电商商机（电商榜单 HTML，需动态渲染）==========
        # Amazon Best Sellers 真实榜单页，需 playwright 动态加载；抓取商品名/价格/排名
        ('亚马逊热销榜-电子办公', 'html', 'https://www.amazon.com/Best-Sellers/zgbs/electronics',
         '{"dynamic": true, "max_items": 20}', '卫星通信,遥感,通信终端,办公,电子', '信息技术', '海外', 0, 24, '电商商机'),
        # ========== 3. 企业客源（企业信用公示 HTML，需动态渲染）==========
        # 国家企业信用信息公示系统真实入口，需 playwright 模拟搜索；按关键词检索新注册企业
        ('国家企业信用公示-新注册企业', 'html', 'https://www.gsxt.gov.cn/',
         '{"dynamic": true, "max_items": 20, "search_type": "enterprise"}',
         '卫星,遥感,通信,智能体,科技', '信息技术', '全国', 0, 48, '企业客源'),
        # ========== 5. 舆情痛点（垂直社区 HTML，需动态渲染）==========
        # 知乎热榜真实页面，需 playwright 动态渲染；抓取用户讨论中的需求痛点
        ('知乎热榜-需求痛点', 'html', 'https://www.zhihu.com/hot',
         '{"dynamic": true, "max_items": 20}', '卫星,遥感,通信,智能体,采购,招标', '信息技术', '全国', 0, 12, '舆情痛点'),
        # 百度贴吧真实搜索页，按关键词抓取用户吐槽
        ('百度贴吧-行业痛点', 'html', 'https://tieba.baidu.com/f?kw=%CE%C0%D0%C7%B5%D8%C7%F2',
         '{"dynamic": false, "max_items": 15}', '卫星,遥感,通信,智能体', '信息技术', '全国', 0, 24, '舆情痛点'),
        # ========== AI 智能体互联网搜索（五大能力域，默认启用，无需 playwright）==========
        # AI 搜索用 DuckDuckGo 搜索引擎 + LLM 提取结构化线索，仅需网络无需动态渲染
        # 遥感领域聚焦安徽省内采购
        ('AI搜索-招投标监控', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '卫星遥感,遥感数据,安徽,卫星通信,通信终端', '信息技术', '安徽', 1, 12, '招投标监控'),
        ('AI搜索-电商商机', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '卫星通信,通信终端,智能体,遥感', '信息技术', '全国', 1, 24, '电商商机'),
        ('AI搜索-企业客源', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '卫星,遥感,通信,智能体,科技', '信息技术', '全国', 1, 48, '企业客源'),
        ('AI搜索-竞品情报', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '卫星通信,通信终端,智能体,遥感', '信息技术', '全国', 1, 24, '竞品情报'),
        ('AI搜索-舆情痛点', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '卫星,遥感,通信,智能体,采购,招标', '信息技术', '全国', 1, 24, '舆情痛点'),
        # ========== 军采监控：按9大业务领域配置专用 AI 搜索源 ==========
        # 用户关注：采购站/装备健康/模拟器/雷达/卫通/智能体/仿真/软件/卫星/靶场/对抗
        # 每个源覆盖1-2个相关领域，max_queries=3 确保每个领域有足够查询覆盖
        # 雷达电子 + 电子对抗
        ('AI搜索-军采雷达对抗', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '雷达,相控阵,对抗,电子战,电子对抗', '雷达电子', '全国', 1, 12, '军采监控'),
        # 仿真模拟 + 模拟器
        ('AI搜索-军采仿真模拟', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '仿真,半实物仿真,模拟器,训练模拟器,虚拟训练', '仿真模拟', '全国', 1, 12, '军采监控'),
        # 卫通 + 卫星遥感
        ('AI搜索-军采卫通卫星', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '卫通,卫星通信,通信终端,卫星,遥感', '卫通卫星', '全国', 1, 12, '军采监控'),
        # 装备健康 + 靶场试验
        ('AI搜索-军采装备靶场', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '装备健康,健康管理,PHM,靶场,试验场', '装备健康', '全国', 1, 12, '军采监控'),
        # AI智能体 + 软件
        ('AI搜索-军采智能软件', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '智能体,人工智能,大模型,软件,信息化,指挥控制', 'AI智能体', '全国', 1, 12, '军采监控'),
        # 装备通用（武器/军用/国防）
        ('AI搜索-军采装备通用', 'ai_search', '',
         '{"max_items": 15, "max_queries": 3}', '装备,武器,军用,国防,装备采购', '军工装备', '全国', 1, 12, '军采监控'),
    ]
    for s in sources:
        try:
            cursor.execute("SELECT id FROM lead_sources WHERE name=?", (s[0],))
            if cursor.fetchone():
                # 已存在则补全 category（兼容旧源）
                if len(s) >= 10:
                    cursor.execute("UPDATE lead_sources SET category=? WHERE name=? AND (category IS NULL OR category='')", (s[9], s[0]))
                continue
            cursor.execute("""
                INSERT INTO lead_sources (name, source_type, url, config, keywords, industry,
                                          region, enabled, interval_hours, last_scraped_at, created_at, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
            """, (s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], s[8], now, s[9]))
        except:
            pass
    # 停用 URL 为网站首页（非真正 RSS 订阅地址）的旧 RSS 源，避免抓不到数据
    # AI 搜索源（ai_search）已替代这些源，无需 playwright 即可搜到真实数据
    try:
        cursor.execute("""
            UPDATE lead_sources SET enabled=0
            WHERE source_type='rss' AND category='招投标监控'
            AND url IN ('http://www.plap.cn/', 'https://www.ggzy.gov.cn/', 'http://bulletin.cebpubservice.com/')
        """)
    except Exception:
        pass
    # 停用旧的泛关键词军采源（被新的9大领域专用源替代）
    try:
        cursor.execute("""
            UPDATE lead_sources SET enabled=0
            WHERE source_type='ai_search' AND category='军采监控'
            AND name IN ('AI搜索-军采装备', 'AI搜索-军采信息化')
        """)
    except Exception:
        pass
    # 停用需要 playwright 的 HTML 源（环境中无 playwright 时抓不到数据，避免无效抓取）
    try:
        cursor.execute("UPDATE lead_sources SET enabled=0 WHERE source_type='html'")
    except Exception:
        pass


def _init_user_roles_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE user_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                UNIQUE(username, role)
            )
        """)
    except:
        pass
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO user_roles (username, role)
            SELECT username, role FROM users
            WHERE role IS NOT NULL AND role != ''
        """)
    except:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT '在职'")
    except:
        pass
    try:
        cursor.execute("UPDATE users SET status = '在职' WHERE status IS NULL OR status = ''")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN department TEXT DEFAULT ''")
    except:
        pass


def _init_business_table(cursor):
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN address TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN customer_relation TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN weekly_plan TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN next_week_plan TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN plan_week TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE business ADD COLUMN note TEXT")
    except:
        pass
    try:
        cursor.execute("""
            CREATE TABLE business_plan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER,
                plan_type TEXT,
                week_label TEXT,
                content TEXT,
                created_at TEXT,
                created_by TEXT,
                FOREIGN KEY (business_id) REFERENCES business(id)
            )
        """)
    except:
        pass


def _init_contracts_table(cursor):
    """合同表迁移：新增 cust_id 字段，建立合同↔客户直接关联（与 business.cust_id 对齐）。"""
    try:
        cursor.execute("ALTER TABLE contracts ADD COLUMN cust_id INTEGER")
    except:
        pass


def _init_operation_logs_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE operation_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                operation TEXT NOT NULL,
                module TEXT NOT NULL,
                detail TEXT,
                ip_address TEXT,
                created_at TEXT NOT NULL,
                is_read INTEGER DEFAULT 0
            )
        """)
    except:
        pass
    try:
        cursor.execute("ALTER TABLE operation_logs ADD COLUMN is_read INTEGER DEFAULT 0")
    except:
        pass


def _init_visits_table(cursor):
    try:
        cursor.execute("""
            CREATE TABLE visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cust_id INTEGER,
                visitor_id TEXT,
                plan_date TEXT NOT NULL,
                plan_time TEXT,
                actual_date TEXT,
                actual_time TEXT,
                purpose TEXT,
                status TEXT DEFAULT 'planned',
                result TEXT,
                location TEXT,
                contact_person TEXT,
                notes TEXT,
                work_type TEXT DEFAULT 'visit',
                work_content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cust_id) REFERENCES customers(id)
            )
        """)
    except:
        pass
    try:
        cursor.execute("ALTER TABLE visits ADD COLUMN location TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE visits ADD COLUMN contact_person TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE visits ADD COLUMN notes TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE visits ADD COLUMN work_type TEXT DEFAULT 'visit'")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE visits ADD COLUMN work_content TEXT")
    except:
        pass


def _init_follow_logs_table(cursor):
    """客户跟进日志表。"""
    try:
        cursor.execute("""
            CREATE TABLE follow_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_type TEXT NOT NULL,
                ref_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                content TEXT,
                log_time TEXT DEFAULT CURRENT_TIMESTAMP,
                next_action TEXT,
                next_date TEXT,
                status TEXT DEFAULT '跟进中',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_follow_ref ON follow_logs(ref_type, ref_id)")
    except:
        pass
    try:
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_follow_user ON follow_logs(user_id)")
    except:
        pass


def _init_enterprise_table(cursor):
    """企业信息库表。"""
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enterprises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                established_date TEXT,
                location TEXT,
                personnel_size TEXT,
                brief TEXT,
                registered_capital TEXT,
                business_scope TEXT,
                main_qualifications TEXT,
                main_products TEXT,
                relationship_status TEXT DEFAULT '未接触',
                cooperation_opportunities TEXT,
                website TEXT,
                contact_person TEXT,
                contact_info TEXT,
                owner_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    except Exception:
        pass
    # 为已有表补齐缺失字段
    for col, decl in [
        ('established_date', 'TEXT'),
        ('location', 'TEXT'),
        ('personnel_size', 'TEXT'),
        ('brief', 'TEXT'),
        ('registered_capital', 'TEXT'),
        ('business_scope', 'TEXT'),
        ('main_qualifications', 'TEXT'),
        ('main_products', 'TEXT'),
        ('relationship_status', "TEXT DEFAULT '未接触'"),
        ('cooperation_opportunities', 'TEXT'),
        ('website', 'TEXT'),
        ('contact_person', 'TEXT'),
        ('contact_info', 'TEXT'),
        ('owner_id', 'TEXT'),
        ('updated_at', 'TEXT DEFAULT CURRENT_TIMESTAMP'),
    ]:
        try:
            cursor.execute(f"ALTER TABLE enterprises ADD COLUMN {col} {decl}")
        except Exception:
            pass
    # 关联拜访记录的中间表
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS enterprise_visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enterprise_id INTEGER NOT NULL,
                visit_id INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (enterprise_id) REFERENCES enterprises(id),
                FOREIGN KEY (visit_id) REFERENCES visits(id)
            )
        """)
    except Exception:
        pass
    try:
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ent_visit ON enterprise_visits(enterprise_id, visit_id)")
    except Exception:
        pass


def record_operation_log(username, operation, module, detail=''):
    try:
        db = get_db()
        cursor = db.cursor()
        ip_address = request.remote_addr if request else ''
        cursor.execute("""
            INSERT INTO operation_logs (username, operation, module, detail, ip_address, created_at, is_read)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (username, operation, module, detail, ip_address, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        db.commit()
    except Exception as e:
        pass


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def check_password(password: str, hash_val: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hash_val.encode('utf-8'))


def create_token(username: str, name: str, role: str) -> str:
    token = str(uuid.uuid4())
    expires = datetime.now() + timedelta(hours=24)
    db = get_db()
    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO tokens (token, username, name, role, expires)
        VALUES (?, ?, ?, ?, ?)
    ''', (token, username, name, role, expires.strftime('%Y-%m-%d %H:%M:%S')))
    db.commit()
    return token


def verify_token(token: str):
    if not token:
        return None
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM tokens WHERE token = ?', (token,))
    row = cursor.fetchone()
    if not row:
        return None
    expires = datetime.strptime(row['expires'], '%Y-%m-%d %H:%M:%S')
    if datetime.now() > expires:
        cursor.execute('DELETE FROM tokens WHERE token = ?', (token,))
        db.commit()
        return None
    return {
        'username': row['username'],
        'name': row['name'],
        'role': row['role'],
        'expires': expires
    }


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        payload = verify_token(token)
        if not payload:
            return jsonify({'code': 401, 'message': '登录已过期', 'data': None})
        request.current_user = payload
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @token_required
    def decorated(*args, **kwargs):
        payload = request.current_user
        if payload['role'] not in ('主任', '院长'):
            return jsonify({'code': 403, 'message': '权限不足', 'data': None})
        return f(*args, **kwargs)
    return decorated


def check_login_rate_limit(ip_address):
    now = time.time()
    if ip_address in LOGIN_ATTEMPTS:
        LOGIN_ATTEMPTS[ip_address] = [t for t in LOGIN_ATTEMPTS[ip_address] if now - t < LOGIN_WINDOW_SECONDS]
        if len(LOGIN_ATTEMPTS[ip_address]) >= LOGIN_MAX_ATTEMPTS:
            oldest = LOGIN_ATTEMPTS[ip_address][0]
            wait_seconds = int(LOGIN_WINDOW_SECONDS - (now - oldest))
            return False, wait_seconds
    return True, 0


def record_login_attempt(ip_address):
    LOGIN_ATTEMPTS[ip_address].append(time.time())


def reset_login_rate_limit(ip_address=None):
    if ip_address:
        LOGIN_ATTEMPTS.pop(ip_address, None)
    else:
        LOGIN_ATTEMPTS.clear()


INACTIVE_DAYS = 100


def cleanup_inactive_customers():
    from datetime import datetime, timedelta
    cutoff_date = (datetime.now() - timedelta(days=INACTIVE_DAYS)).strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.id, c.name, c.company, c.last_follow, c.created_at, c.owner_id
            FROM customers c
            WHERE (c.last_follow IS NOT NULL AND c.last_follow < ?)
               OR (c.last_follow IS NULL AND c.created_at < ?)
        """, (cutoff_date, cutoff_date))
        
        customers_to_delete = cursor.fetchall()
        
        deleted_count = 0
        for customer in customers_to_delete:
            cust_id = customer['id']
            try:
                cursor.execute("UPDATE business SET cust_id = NULL WHERE cust_id = ?", (cust_id,))
                cursor.execute("DELETE FROM customers WHERE id = ?", (cust_id,))
                deleted_count += 1
            except Exception:
                conn.rollback()
        
        if deleted_count > 0:
            conn.commit()
        else:
            conn.rollback()
        
        conn.close()
        return deleted_count
    except Exception:
        return 0


def update_customer_last_follow(customer_id):
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE customers SET last_follow = ? WHERE id = ?",
            (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), customer_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def setup_extensions(app: Flask):
    app.teardown_appcontext(close_db)

    @app.after_request
    def after_request(response):
        origin = request.headers.get('Origin', '')
        if origin in ALLOWED_ORIGINS:
            response.headers.add('Access-Control-Allow-Origin', origin)
            response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,PATCH,OPTIONS')
        return response

    @app.route('/api/', methods=['OPTIONS'])
    def options():
        return jsonify({'code': 200, 'message': 'OK', 'data': None})
