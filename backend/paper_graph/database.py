"""论文图谱管理工具 - 数据模型与存储层。"""

import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "papers.db"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            id TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            core_contribution TEXT,
            published_date TEXT,
            updated_date TEXT,
            categories TEXT,
            pdf_path TEXT,
            md_path TEXT,
            source TEXT DEFAULT 'local',
            arxiv_url TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            enhanced_at TEXT
        )
    """)

    # 兼容已存在的旧库：动态添加 md_path 列
    try:
        cur.execute("ALTER TABLE papers ADD COLUMN md_path TEXT")
    except sqlite3.OperationalError:
        pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT,
            affiliation TEXT,
            UNIQUE(name, affiliation)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS institutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            normalized_name TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_authors (
            paper_id TEXT,
            author_id INTEGER,
            author_order INTEGER,
            PRIMARY KEY (paper_id, author_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_institutions (
            paper_id TEXT,
            institution_id INTEGER,
            PRIMARY KEY (paper_id, institution_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (institution_id) REFERENCES institutions(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            lead_institution_id INTEGER,
            description TEXT,
            FOREIGN KEY (lead_institution_id) REFERENCES institutions(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            team_id INTEGER,
            author_id INTEGER,
            role TEXT DEFAULT 'member',
            PRIMARY KEY (team_id, author_id),
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS paper_teams (
            paper_id TEXT,
            team_id INTEGER,
            PRIMARY KEY (paper_id, team_id),
            FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE,
            FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_papers_source ON papers(source)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_papers_published ON papers(published_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_authors_paper ON paper_authors(paper_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_paper_authors_author ON paper_authors(author_id)")

    # 聊天会话与消息历史
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            papers TEXT,
            tool_calls TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
        )
    """)
    # 兼容已存在的旧库：动态添加 tool_calls 列
    try:
        cur.execute("ALTER TABLE chat_messages ADD COLUMN tool_calls TEXT")
    except sqlite3.OperationalError:
        pass
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_session ON chat_messages(session_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_messages_created ON chat_messages(created_at)")

    conn.commit()
    conn.close()


def upsert_paper(conn: sqlite3.Connection, paper: dict) -> None:
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO papers (id, title, abstract, published_date, updated_date, categories, pdf_path, source, arxiv_url)
        VALUES (:id, :title, :abstract, :published_date, :updated_date, :categories, :pdf_path, :source, :arxiv_url)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            abstract=excluded.abstract,
            updated_date=excluded.updated_date,
            categories=excluded.categories,
            pdf_path=excluded.pdf_path,
            source=excluded.source,
            arxiv_url=excluded.arxiv_url
    """, paper)


def get_paper(conn: sqlite3.Connection, paper_id: str) -> Optional[dict]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def list_papers(db_path: Optional[Path] = None, source: Optional[str] = None) -> pd.DataFrame:
    conn = get_connection(db_path)
    sql = "SELECT * FROM papers"
    params = ()
    if source:
        sql += " WHERE source = ?"
        params = (source,)
    sql += " ORDER BY published_date DESC"
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    # Ensure JSON-safe output by replacing NaN/NaT with None
    df = df.where(pd.notnull(df), None)
    return df


# ──────────────────────────────
# 聊天会话与消息
# ──────────────────────────────

def create_chat_session(conn: sqlite3.Connection, session_id: str, title: str = "") -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO chat_sessions (id, title) VALUES (?, ?)",
        (session_id, title),
    )
    cur.execute(
        "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (session_id,),
    )
    conn.commit()


def update_chat_session_title(conn: sqlite3.Connection, session_id: str, title: str) -> None:
    cur = conn.cursor()
    cur.execute(
        "UPDATE chat_sessions SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (title, session_id),
    )
    conn.commit()


def get_chat_session(conn: sqlite3.Connection, session_id: str) -> Optional[dict]:
    cur = conn.cursor()
    cur.execute("SELECT * FROM chat_sessions WHERE id = ?", (session_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def list_chat_sessions(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in cur.fetchall()]


def delete_chat_session(conn: sqlite3.Connection, session_id: str) -> None:
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))
    cur.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    conn.commit()


def add_chat_message(
    conn: sqlite3.Connection,
    message_id: str,
    session_id: str,
    role: str,
    content: str,
    papers: Optional[str] = None,
    tool_calls: Optional[str] = None,
) -> None:
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO chat_messages (id, session_id, role, content, papers, tool_calls) VALUES (?, ?, ?, ?, ?, ?)",
        (message_id, session_id, role, content, papers, tool_calls),
    )
    cur.execute(
        "UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (session_id,),
    )
    conn.commit()


def get_chat_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    )
    return [dict(row) for row in cur.fetchall()]
