# database.py
import psycopg2
from psycopg2.extras import RealDictCursor
from config import POSTGRES_CONFIG
from typing import Optional, Tuple
from datetime import datetime

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
    # Ensure answers table has region/subregion columns
    cur.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS region TEXT;")
    cur.execute("ALTER TABLE answers ADD COLUMN IF NOT EXISTS subregion TEXT;")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_regions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        region TEXT,
        subregion TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)
    # Backfill and enforce NOT NULL for region/subregion in case the table pre-existed
    cur.execute("UPDATE user_regions SET region = 'Unknown' WHERE region IS NULL;")
    cur.execute("UPDATE user_regions SET subregion = 'Unknown' WHERE subregion IS NULL;")
    try:
        cur.execute("ALTER TABLE user_regions ALTER COLUMN region SET NOT NULL;")
    except Exception:
        pass
    try:
        cur.execute("ALTER TABLE user_regions ALTER COLUMN subregion SET NOT NULL;")
    except Exception:
        pass
    conn.commit()
    cur.close()
    conn.close()

def delete_answer_current_month(user_id: int, question_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM answers
        WHERE user_id = %s AND question_id = %s
          AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW());
        """,
        (user_id, question_id),
    )
    conn.commit()
    cur.close()
    conn.close()

def save_answer(user_id: int, question_id: int, question_text: str, answer: str, region: str, subregion: str):
    conn = get_connection()
    cur = conn.cursor()
    # Ensure only one answer per user/question per month by replacing any existing one
    cur.execute(
        """
        DELETE FROM answers
        WHERE user_id = %s AND question_id = %s
          AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW());
        """,
        (user_id, question_id),
    )
    cur.execute(
        """
        INSERT INTO answers (user_id, question_id, question_text, answer, region, subregion)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (user_id, question_id, question_text, answer, region, subregion),
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
    cur.execute(
        """
        SELECT COUNT(*) FROM answers
         WHERE user_id = %s
           AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW());
        """,
        (user_id,),
    )
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
    cur.execute(
        """
        SELECT user_id, COUNT(*) AS cnt
        FROM answers
        WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW())
        GROUP BY user_id
        HAVING COUNT(*) < %s AND COUNT(*) > 0;
        """,
        (total_questions,),
    )
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

def get_latest_region_timestamp_this_month(user_id: int) -> Optional[datetime]:
    """Return the datetime of the latest region record this month for a user."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT created_at
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
    # row[0] is already a datetime from psycopg2
    return row[0]

def reset_current_month_data(user_id: int) -> None:
    """Delete this user's answers and region for the current month to restart the survey."""
    conn = get_connection()
    cur = conn.cursor()
    # Delete answers for this month
    cur.execute(
        """
        DELETE FROM answers
        WHERE user_id = %s
          AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW());
        """,
        (user_id,),
    )
    # Delete region for this month
    cur.execute(
        """
        DELETE FROM user_regions
        WHERE user_id = %s
          AND DATE_TRUNC('month', created_at) = DATE_TRUNC('month', NOW());
        """,
        (user_id,),
    )
    conn.commit()
    cur.close()
    conn.close()
