"""重置 AI 搜索源的抓取时间戳，让调度器重新抓取。"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'crm_app.db')
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("UPDATE lead_sources SET last_scraped_at=NULL WHERE source_type='ai_search'")
print('reset', c.rowcount, 'ai_search sources')
conn.commit()
conn.close()
