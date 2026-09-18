# database.py
# -*- coding: utf-8 -*-

import sqlite3

DB_PATH = "bot_memory.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS messages ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  user_id INTEGER NOT NULL,"
        "  role TEXT NOT NULL,"
        "  text TEXT NOT NULL,"
        "  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_id ON messages(user_id)"
    )

    # جدول نتائج الاختبارات
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS quiz_results ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  user_id INTEGER NOT NULL,"
        "  topic TEXT,"
        "  score INTEGER NOT NULL,"
        "  total INTEGER NOT NULL,"
        "  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_quiz_user_id ON quiz_results(user_id)"
    )

    conn.commit()
    conn.close()
    print("قاعدة البيانات جاهزة.")


def save_message(user_id, role, text):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (user_id, role, text) VALUES (?, ?, ?)",
        (user_id, role, text)
    )
    conn.commit()
    conn.close()


def get_recent_messages(user_id, limit=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, text FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r, "text": t} for r, t in reversed(rows)]


def clear_user_messages(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def get_all_messages(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, text, timestamp FROM messages WHERE user_id = ? ORDER BY id ASC",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


# ==================== نتائج الاختبارات ====================

def save_quiz_result(user_id, topic, score, total):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO quiz_results (user_id, topic, score, total) VALUES (?, ?, ?, ?)",
        (user_id, topic, score, total)
    )
    conn.commit()
    conn.close()


def get_user_stats(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*), SUM(score), SUM(total) FROM quiz_results WHERE user_id = ?",
        (user_id,)
    )
    row = cursor.fetchone()
    conn.close()

    quizzes_count = row[0] or 0
    total_score = row[1] or 0
    total_possible = row[2] or 0

    avg_percent = 0
    if total_possible > 0:
        avg_percent = round((total_score / total_possible) * 100, 1)

    return {
        "quizzes_count": quizzes_count,
        "total_score": total_score,
        "total_possible": total_possible,
        "avg_percent": avg_percent,
    }


def get_last_results(user_id, limit=5):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT topic, score, total, timestamp FROM quiz_results WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows