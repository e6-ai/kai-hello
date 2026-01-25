import aiosqlite
import os
from datetime import datetime
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "/data/kai.db")

async def init_db():
    """Initialize the database with required tables."""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS thoughts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT,
                ip_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def get_thoughts(limit: int = 50):
    """Get recent thoughts."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, content, created_at FROM thoughts ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def add_thought(content: str):
    """Add a new thought."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO thoughts (content) VALUES (?)",
            (content,)
        )
        await db.commit()
        return cursor.lastrowid

async def log_question(question: str, answer: str, ip_hash: str):
    """Log a question and its answer."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO questions (question, answer, ip_hash) VALUES (?, ?, ?)",
            (question, answer, ip_hash)
        )
        await db.commit()
