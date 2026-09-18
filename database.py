# database.py

import sqlite3
import bcrypt
import pandas as pd
import streamlit as st
from contextlib import contextmanager
from datetime import datetime, date

DB_PATH = "crm_app.db"

# ========== 1. 连接管理 ==========
@contextmanager
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        st.error(f"数据库操作失败: {e}")
        raise
    finally:
        conn.close()

def query_df(sql, params=()):
    with get_db_connection() as conn:
        return pd.read_sql(sql, conn, params=params)

def execute_sql(sql, params=()):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.rowcount

# ========== 2. 辅助函数：添加列 ==========
def _add_column_if_not_exists(conn, table, column, col_def):
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    existing = [col[1] for col in cursor.fetchall()]
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")
        conn.commit()

# ========== 3. 数据库初始化 ==========
def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # ---------- 3.1 创建基础表 ----------
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT,
                level TEXT,
                source TEXT,
                owner_id TEXT,
                last_follow DATE,
                created_at DATE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS business (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cust_id INTEGER,
                title TEXT NOT NULL,
                amount REAL,
                stage TEXT,
                predict_date DATE,
                owner_id TEXT,
                created_at DATE DEFAULT CURRENT_DATE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                b_id INTEGER,
                contract_no TEXT UNIQUE,
                total_amt REAL,
                paid_amt REAL DEFAULT 0,
                sign_date DATE,
                owner_id TEXT,
                status TEXT DEFAULT '执行中'
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS follow_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref_type TEXT,
                ref_id INTEGER,
                user_id TEXT,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS business_stage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER,
                old_stage TEXT,
                new_stage TEXT,
                user_id TEXT,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payment_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contract_id INTEGER NOT NULL,
                payment_date DATE NOT NULL,
                amount REAL NOT NULL,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(contract_id) REFERENCES contracts(id) ON DELETE CASCADE
            )
        ''')
        # work_hours 表：business_id 设为可空（兼容旧数据，但新数据使用 project_type/project_id）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS work_hours (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_id INTEGER,
                project_type TEXT DEFAULT 'business',
                project_id INTEGER,
                user_id TEXT NOT NULL,
                work_date DATE NOT NULL,
                start_time TIME,
                end_time TIME,
                overtime_start TIME,
                overtime_end TIME,
                overtime_hours REAL DEFAULT 0,
                hours REAL NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'pending',
                submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approve_time TIMESTAMP,
                approver_id TEXT,
                reject_reason TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_hourly_rate (
                user_id TEXT PRIMARY KEY,
                hourly_rate REAL DEFAULT 200.0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_roles (
                username TEXT,
                role TEXT,
                PRIMARY KEY (username, role),
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS project_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_type TEXT DEFAULT 'business',
                project_id INTEGER,
                user_id TEXT NOT NULL,
                assigned_by TEXT NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_type, project_id, user_id)
            )
        ''')


        # 在 database.py 的 init_db() 中添加/迁移 costs 表
        # 检查是否存在旧表 project_costs，若存在则重命名备份
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_costs'")
        if cursor.fetchone():
            cursor.execute("ALTER TABLE project_costs RENAME TO project_costs_old")
            cursor.execute('''
                CREATE TABLE costs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_type TEXT NOT NULL,   -- 'business' 或 'contract'
                    project_id INTEGER NOT NULL,
                    cost_type TEXT NOT NULL,      -- 'history', 'travel', 'review', 'entertainment', 'other'
                    amount REAL NOT NULL,
                    description TEXT,
                    cost_date DATE,
                    created_by TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 迁移旧数据（原 business_id 转为 project_type='business'）
            try:
                cursor.execute('''
                    INSERT INTO costs (project_type, project_id, cost_type, amount, description, cost_date, created_by, created_at)
                    SELECT 'business', business_id, cost_type, amount, description, cost_date, created_by, created_at
                    FROM project_costs_old
                    WHERE business_id IS NOT NULL
                ''')
                st.info("已迁移旧版成本数据到新表")
            except Exception as e:
                st.warning(f"旧数据迁移失败，请手动处理: {e}")
            cursor.execute("DROP TABLE project_costs_old")
        else:
            # 直接创建新表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS costs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_type TEXT NOT NULL,
                    project_id INTEGER NOT NULL,
                    cost_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    description TEXT,
                    cost_date DATE,
                    created_by TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

        # 为 business 和 contracts 表增加 total_cost 字段（如果还没有）
        _add_column_if_not_exists(conn, 'business', 'total_cost', 'total_cost REAL DEFAULT 0')
        _add_column_if_not_exists(conn, 'contracts', 'total_cost', 'total_cost REAL DEFAULT 0')


        # ---------- 3.2 字段迁移（兼容旧库） ----------
        _add_column_if_not_exists(conn, 'contracts', 'sign_date', 'sign_date DATE')
        _add_column_if_not_exists(conn, 'contracts', 'owner_id', 'owner_id TEXT')
        _add_column_if_not_exists(conn, 'contracts', 'contract_name', 'contract_name TEXT')
        _add_column_if_not_exists(conn, 'contracts', 'classification', 'classification TEXT')
        _add_column_if_not_exists(conn, 'contracts', 'is_audit', 'is_audit INTEGER DEFAULT 0')
        _add_column_if_not_exists(conn, 'contracts', 'pending_acceptance_amount', 'pending_acceptance_amount REAL DEFAULT 0')
        _add_column_if_not_exists(conn, 'contracts', 'cost', 'cost REAL DEFAULT 0')
        _add_column_if_not_exists(conn, 'contracts', 'gross_profit', 'gross_profit REAL DEFAULT 0')
        _add_column_if_not_exists(conn, 'contracts', 'acceptance_date', 'acceptance_date DATE')
        _add_column_if_not_exists(conn, 'contracts', 'expected_income_date', 'expected_income_date DATE')
        _add_column_if_not_exists(conn, 'contracts', 'expected_income_year', 'expected_income_year REAL DEFAULT 0')
        _add_column_if_not_exists(conn, 'contracts', 'business_type', 'business_type TEXT')
        _add_column_if_not_exists(conn, 'contracts', 'project_order_no', 'project_order_no TEXT')

        _add_column_if_not_exists(conn, 'business', 'probability', 'probability INTEGER DEFAULT 0')
        _add_column_if_not_exists(conn, 'business', 'tax_rate', 'tax_rate REAL DEFAULT 0')
        _add_column_if_not_exists(conn, 'business', 'expected_income_year', 'expected_income_year REAL DEFAULT 0')
        _add_column_if_not_exists(conn, 'business', 'expected_cost_year', 'expected_cost_year REAL DEFAULT 0')
        _add_column_if_not_exists(conn, 'business', 'expected_income_month', 'expected_income_month TEXT')
        _add_column_if_not_exists(conn, 'business', 'implementation_status', 'implementation_status TEXT')
        _add_column_if_not_exists(conn, 'business', 'status', "status TEXT DEFAULT 'active'")
        _add_column_if_not_exists(conn, 'business', 'project_manager', 'project_manager TEXT')

        _add_column_if_not_exists(conn, 'follow_logs', 'log_time', 'log_time TIMESTAMP')
        _add_column_if_not_exists(conn, 'follow_logs', 'subject', 'subject TEXT')
        _add_column_if_not_exists(conn, 'follow_logs', 'participants', 'participants TEXT')
        _add_column_if_not_exists(conn, 'follow_logs', 'location', 'location TEXT')
        _add_column_if_not_exists(conn, 'follow_logs', 'next_plan', 'next_plan TEXT')

        _add_column_if_not_exists(conn, 'work_hours', 'project_type', "project_type TEXT DEFAULT 'business'")
        _add_column_if_not_exists(conn, 'work_hours', 'project_id', 'project_id INTEGER')
        _add_column_if_not_exists(conn, 'work_hours', 'start_time', 'start_time TIME')
        _add_column_if_not_exists(conn, 'work_hours', 'end_time', 'end_time TIME')
        _add_column_if_not_exists(conn, 'work_hours', 'overtime_start', 'overtime_start TIME')
        _add_column_if_not_exists(conn, 'work_hours', 'overtime_end', 'overtime_end TIME')
        _add_column_if_not_exists(conn, 'work_hours', 'overtime_hours', 'overtime_hours REAL DEFAULT 0')
        # 在 database.py 的 init_db() 中，添加 phone 列到 customers 表
        _add_column_if_not_exists(conn, 'customers', 'phone', 'phone TEXT')

        # ---------- 3.3 关键迁移：将 work_hours.business_id 改为可空 ----------
        cursor.execute("PRAGMA table_info(work_hours)")
        columns_info = cursor.fetchall()
        for col in columns_info:
            if col[1] == 'business_id' and col[3] == 1:  # notnull=1
                # 重建表以移除 NOT NULL 约束
                cursor.execute('''
                    CREATE TABLE work_hours_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        business_id INTEGER,
                        project_type TEXT DEFAULT 'business',
                        project_id INTEGER,
                        user_id TEXT NOT NULL,
                        work_date DATE NOT NULL,
                        start_time TIME,
                        end_time TIME,
                        overtime_start TIME,
                        overtime_end TIME,
                        overtime_hours REAL DEFAULT 0,
                        hours REAL NOT NULL,
                        description TEXT,
                        status TEXT DEFAULT 'pending',
                        submit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        approve_time TIMESTAMP,
                        approver_id TEXT,
                        reject_reason TEXT
                    )
                ''')
                cursor.execute('''
                    INSERT INTO work_hours_new
                    SELECT id, business_id, project_type, project_id, user_id, work_date,
                           start_time, end_time, overtime_start, overtime_end, overtime_hours,
                           hours, description, status, submit_time, approve_time, approver_id, reject_reason
                    FROM work_hours
                ''')
                cursor.execute("DROP TABLE work_hours")
                cursor.execute("ALTER TABLE work_hours_new RENAME TO work_hours")
                # 重建索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_hours_project ON work_hours(project_type, project_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_hours_user ON work_hours(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_hours_status ON work_hours(status)")
                conn.commit()
                break

        # 数据迁移：将旧 business_id 填充到 project_type/project_id
        cursor.execute("UPDATE work_hours SET project_type='business', project_id=business_id WHERE business_id IS NOT NULL AND project_id IS NULL")

        # ---------- 3.4 处理 project_assignments 旧表结构迁移 ----------
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='project_assignments'")
        table_def = cursor.fetchone()
        if table_def:
            cursor.execute("PRAGMA table_info(project_assignments)")
            cols = [col[1] for col in cursor.fetchall()]
            if 'business_id' in cols:
                cursor.execute('''
                    CREATE TABLE project_assignments_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_type TEXT DEFAULT 'business',
                        project_id INTEGER,
                        user_id TEXT NOT NULL,
                        assigned_by TEXT NOT NULL,
                        assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(project_type, project_id, user_id)
                    )
                ''')
                cursor.execute('''
                    INSERT INTO project_assignments_new (id, project_type, project_id, user_id, assigned_by, assigned_at)
                    SELECT id, 'business', business_id, user_id, assigned_by, assigned_at
                    FROM project_assignments
                    WHERE business_id IS NOT NULL
                ''')
                cursor.execute("DROP TABLE project_assignments")
                cursor.execute("ALTER TABLE project_assignments_new RENAME TO project_assignments")
                conn.commit()

        # ---------- 3.5 创建索引 ----------
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_customers_owner ON customers(owner_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_business_owner ON business(owner_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contracts_owner ON contracts(owner_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_follow_logs_ref ON follow_logs(ref_type, ref_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_payment_records_contract ON payment_records(contract_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_hours_project ON work_hours(project_type, project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_hours_user ON work_hours(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_work_hours_status ON work_hours(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_project ON project_assignments(project_type, project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_roles_username ON user_roles(username)")

        # ---------- 3.6 初始化默认用户 ----------
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_users = {
                "yewei": {"password": "abc.123456", "name": "叶伟", "role": "主任"},
                "liuyingjun": {"password": "123", "name": "刘颖俊", "role": "销售"},
                "zhouchen": {"password": "123", "name": "周辰", "role": "销售"},
                "pangfeng": {"password": "123", "name": "庞峰", "role": "销售"},
                "wangyang": {"password": "123", "name": "汪洋", "role": "销售"},
                "qianhaiming": {"password": "123", "name": "钱海明", "role": "销售"}
            }
            for username, info in default_users.items():
                pwd_hash = bcrypt.hashpw(info["password"].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute(
                    "INSERT INTO users (username, password_hash, name, role) VALUES (?, ?, ?, ?)",
                    (username, pwd_hash, info["name"], info["role"])
                )
                cursor.execute("INSERT OR IGNORE INTO user_roles (username, role) VALUES (?, ?)", (username, info["role"]))
                cursor.execute("INSERT OR IGNORE INTO user_hourly_rate (user_id, hourly_rate) VALUES (?, ?)", (username, 200.0))
            conn.commit()

        # 为已存在但未在 user_roles 中的用户添加默认角色
        cursor.execute("SELECT username, role FROM users")
        for row in cursor.fetchall():
            username = row['username']
            old_role = row['role']
            cursor.execute("SELECT COUNT(*) FROM user_roles WHERE username = ?", (username,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO user_roles (username, role) VALUES (?, ?)", (username, old_role))
                if old_role == '主任':
                    cursor.execute("INSERT OR IGNORE INTO user_roles (username, role) VALUES (?, ?)", (username, '项目经理'))
            cursor.execute("SELECT COUNT(*) FROM user_hourly_rate WHERE user_id = ?", (username,))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO user_hourly_rate (user_id, hourly_rate) VALUES (?, ?)", (username, 200.0))
        conn.commit()

# ========== 4. 密码哈希辅助函数 ==========
def hash_password(pwd: str) -> str:
    return bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(pwd: str, hashed: str) -> bool:
    if hashed.startswith('$2b$'):
        try:
            return bcrypt.checkpw(pwd.encode('utf-8'), hashed.encode('utf-8'))
        except ValueError:
            return False
    else:
        import hashlib
        return hashlib.sha256(pwd.encode()).hexdigest() == hashed

# ========== 5. 主程序 ==========
if __name__ == "__main__":
    init_db()
    print("数据库初始化完成。")