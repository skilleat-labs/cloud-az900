"""
Database module using aiosqlite for async SQLite operations.
"""

import aiosqlite
import json
import os
from pathlib import Path
from datetime import datetime

DB_PATH = os.getenv('DB_PATH', '/home/quiz.db')


async def init_db():
    """Initialize database tables."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS exams (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                title TEXT NOT NULL,
                question_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                exam_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                score INTEGER,
                total INTEGER,
                time_seconds INTEGER,
                FOREIGN KEY (exam_id) REFERENCES exams(id)
            );

            CREATE TABLE IF NOT EXISTS answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS explanations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(exam_id, question_id)
            );
        """)
        await db.commit()


async def upsert_exam(exam_id: str, filename: str, title: str, question_count: int):
    """Insert or update exam record."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO exams (id, filename, title, question_count, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (exam_id, filename, title, question_count, datetime.now().isoformat())
        )
        await db.commit()


async def get_all_exams() -> list[dict]:
    """Get all exam records."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM exams ORDER BY id"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def create_session(session_id: str, exam_id: str, user_name: str) -> dict:
    """Create a new quiz session."""
    started_at = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO sessions (id, exam_id, user_name, started_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, exam_id, user_name, started_at)
        )
        await db.commit()

    return {
        'id': session_id,
        'exam_id': exam_id,
        'user_name': user_name,
        'started_at': started_at,
    }


async def finish_session(session_id: str, score: int, total: int, time_seconds: int,
                         answers: list[dict]):
    """
    Finalize a session with score, time, and individual answers.
    answers: list of {question_id, user_answer (JSON string), is_correct}
    """
    finished_at = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE sessions
               SET finished_at = ?, score = ?, total = ?, time_seconds = ?
               WHERE id = ?""",
            (finished_at, score, total, time_seconds, session_id)
        )

        # Insert individual answers
        for ans in answers:
            await db.execute(
                """INSERT INTO answers (session_id, question_id, user_answer, is_correct)
                   VALUES (?, ?, ?, ?)""",
                (session_id, ans['question_id'],
                 json.dumps(ans['user_answer'], ensure_ascii=False),
                 1 if ans['is_correct'] else 0)
            )

        await db.commit()


async def get_session(session_id: str) -> dict | None:
    """Get session by ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_session_answers(session_id: str) -> list[dict]:
    """Get all answers for a session."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM answers WHERE session_id = ? ORDER BY id",
            (session_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d['user_answer'] = json.loads(d['user_answer'])
                result.append(d)
            return result


async def get_explanation(exam_id: str, question_id: str) -> str | None:
    """Get cached explanation for a question."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT content FROM explanations WHERE exam_id = ? AND question_id = ?",
            (exam_id, question_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def save_explanation(exam_id: str, question_id: str, content: str):
    """Save explanation to cache."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO explanations (exam_id, question_id, content, created_at)
               VALUES (?, ?, ?, ?)""",
            (exam_id, question_id, content, datetime.now().isoformat())
        )
        await db.commit()


async def get_wrong_stats(exam_id: str | None = None) -> list[dict]:
    """
    문제별 오답 통계. exam_id 지정 시 해당 시험지만, None이면 전체.
    오답률 내림차순 정렬.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if exam_id:
            query = """
                SELECT
                    s.exam_id,
                    a.question_id,
                    COUNT(*) AS attempts,
                    SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
                    ROUND(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS wrong_rate
                FROM answers a
                JOIN sessions s ON a.session_id = s.id
                WHERE s.exam_id = ? AND s.finished_at IS NOT NULL
                GROUP BY s.exam_id, a.question_id
                HAVING attempts >= 1
                ORDER BY wrong_rate DESC, wrong_count DESC
            """
            params = (exam_id,)
        else:
            query = """
                SELECT
                    s.exam_id,
                    a.question_id,
                    COUNT(*) AS attempts,
                    SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count,
                    ROUND(SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS wrong_rate
                FROM answers a
                JOIN sessions s ON a.session_id = s.id
                WHERE s.finished_at IS NOT NULL
                GROUP BY s.exam_id, a.question_id
                HAVING attempts >= 1
                ORDER BY wrong_rate DESC, wrong_count DESC
            """
            params = ()
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_leaderboard(exam_id: str, limit: int = 20) -> list[dict]:
    """Get top sessions for an exam, ordered by score desc, time asc."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.id, s.user_name, s.score, s.total, s.time_seconds, s.finished_at
               FROM sessions s
               WHERE s.exam_id = ? AND s.finished_at IS NOT NULL
               ORDER BY s.score DESC, s.time_seconds ASC
               LIMIT ?""",
            (exam_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
