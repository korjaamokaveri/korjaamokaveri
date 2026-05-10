import secrets
from datetime import datetime, timedelta, timezone

from db_init import get_connection


def create_password_reset_token(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    cur.execute("""
        INSERT INTO password_reset_tokens (user_id, token, expires_at)
        VALUES (?, ?, ?)
    """, (user_id, token, expires_at))

    conn.commit()
    conn.close()

    return token


def get_valid_password_reset_token(token: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM password_reset_tokens
        WHERE token = ?
          AND used_at IS NULL
          AND expires_at > CURRENT_TIMESTAMP
        LIMIT 1
    """, (token,))

    row = cur.fetchone()
    conn.close()
    return row


def mark_password_reset_token_used(token: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE password_reset_tokens
        SET used_at = CURRENT_TIMESTAMP
        WHERE token = ?
    """, (token,))

    conn.commit()
    conn.close()


def invalidate_user_reset_tokens(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE password_reset_tokens
        SET used_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
          AND used_at IS NULL
    """, (user_id,))

    conn.commit()
    conn.close()
