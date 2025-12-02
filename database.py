# database.py
import psycopg2
from psycopg2.extras import RealDictCursor
from config import POSTGRES_CONFIG
from typing import Optional, Tuple

def get_connection():
    return psycopg2.connect(**POSTGRES_CONFIG)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS answers (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        question_id INT NOT NULL,
        question_text TEXT,
        answer TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_regions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        region TEXT NOT NULL,
        subregion TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)
    conn.commit()
    cur.close()
    conn.close()

def save_answer(user_id: int, question_id: int, question_text: str, answer: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO answers (user_id, question_id, question_text, answer) VALUES (%s, %s, %s, %s)",
        (user_id, question_id, question_text, answer),
    )
    conn.commit()
    cur.close()
    conn.close()

def get_last_answer_index(user_id: int) -> int:
    """
    Return number of answers the user has submitted THIS MONTH.
    This equals the next question index to send (0-based).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM answers
         WHERE user_id = %s
           AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW());
    """, (user_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count  # next question index

def has_completed_this_month(user_id: int, total_questions: int) -> bool:
    return get_last_answer_index(user_id) >= total_questions

def get_users_with_incomplete_forms(total_questions: int):
    """
    Return list of user_id who have started (>=1 answer this month) but not finished (< total_questions).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, COUNT(*) AS cnt
        FROM answers
        WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())
        GROUP BY user_id
        HAVING COUNT(*) < %s AND COUNT(*) > 0;
    """, (total_questions,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]

def save_region(user_id: int, region: str, subregion: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO user_regions (user_id, region, subregion) VALUES (%s, %s, %s)",
        (user_id, region, subregion),
    )
    conn.commit()
    cur.close()
    conn.close()

def get_region_this_month(user_id: int) -> Optional[Tuple[str, str]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT region, subregion
        FROM user_regions
        WHERE user_id = %s
          AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        (user_id,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    return row[0], row[1]
