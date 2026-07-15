"""
Tiny SQLite data layer for the chat app.
No ORM needed at this scale — just sqlite3 with a couple of helper functions.
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "chat.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New chat',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    conn.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---- Conversations -----------------------------------------------------

def create_conversation(title: str = "New chat") -> dict:
    conn = get_connection()
    conv_id = new_id()
    conn.execute(
        "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
        (conv_id, title, now()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    conn.close()
    return dict(row)


def list_conversations() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM conversations ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation(conv_id: str) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def rename_conversation(conv_id: str, title: str) -> None:
    conn = get_connection()
    conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conv_id))
    conn.commit()
    conn.close()


def delete_conversation(conv_id: str) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()


# ---- Messages ------------------------------------------------------------

def add_message(conv_id: str, role: str, content: str) -> dict:
    conn = get_connection()
    msg_id = new_id()
    conn.execute(
        "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (msg_id, conv_id, role, content, now()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
    conn.close()
    return dict(row)


def get_messages(conv_id: str) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conv_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
