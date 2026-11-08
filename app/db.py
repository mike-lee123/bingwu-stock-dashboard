import sqlite3
import json
import os

DB_FILE = os.path.join(os.path.dirname(__file__), "stock_platform.db")

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    query = """
    CREATE TABLE IF NOT EXISTS research_jobs (
        id TEXT PRIMARY KEY,
        ticker TEXT NOT NULL,
        status TEXT NOT NULL,
        result TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    with get_connection() as conn:
        conn.execute(query)

def save_job(job_id: str, ticker: str, status: str = "pending"):
    query = """
    INSERT INTO research_jobs (id, ticker, status)
    VALUES (?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET status = excluded.status, updated_at = CURRENT_TIMESTAMP;
    """
    with get_connection() as conn:
        conn.execute(query, (job_id, ticker, status))

def update_job_result(job_id: str, status: str, result: dict = None, error: str = None):
    query = """
    UPDATE research_jobs
    SET status = ?, result = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
    WHERE id = ?;
    """
    result_str = json.dumps(result, ensure_ascii=False) if result else None
    with get_connection() as conn:
        conn.execute(query, (status, result_str, error, job_id))

def get_job(job_id: str):
    query = "SELECT * FROM research_jobs WHERE id = ?;"
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, (job_id,))
        row = cur.fetchone()
        if not row:
            return None
        data = dict(row)
        if data.get("result"):
            try:
                data["result"] = json.loads(data["result"])
            except Exception:
                pass
        return data