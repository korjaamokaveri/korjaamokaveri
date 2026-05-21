from werkzeug.security import generate_password_hash
from db_init import get_connection


def get_user_by_email(email: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE lower(email) = ?", ((email or "").lower().strip(),))
    user = cur.fetchone()
    conn.close()
    return user


def get_user_by_id(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()
    return user
    
def update_user_profile(
    user_id: int,
    full_name: str,
    phone: str,
    address_line1: str,
    postal_code: str,
    city: str,
    country: str,
    customer_type: str,
    company_name: str,
    vat_number: str,
):
    normalized_customer_type = (customer_type or "private").strip().lower()
    if normalized_customer_type not in {"private", "company"}:
        normalized_customer_type = "private"

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET full_name = ?,
            phone = ?,
            address_line1 = ?,
            postal_code = ?,
            city = ?,
            country = ?,
            customer_type = ?,
            company_name = ?,
            vat_number = ?
        WHERE id = ?
    """, (
        (full_name or "").strip(),
        (phone or "").strip(),
        (address_line1 or "").strip(),
        (postal_code or "").strip(),
        (city or "").strip(),
        (country or "").strip(),
        normalized_customer_type,
        (company_name or "").strip(),
        (vat_number or "").strip(),
        user_id,
    ))

    conn.commit()
    conn.close()
    
def ensure_user_profile_columns():
    conn = get_connection()
    cur = conn.cursor()

    columns = [
        "full_name TEXT",
        "phone TEXT",
        "address_line1 TEXT",
        "postal_code TEXT",
        "city TEXT",
        "country TEXT",
        "customer_type TEXT DEFAULT 'private'",
        "company_name TEXT",
        "vat_number TEXT",
        "last_active_at TIMESTAMP",
        "is_online INTEGER DEFAULT 0",
    ]

    for column in columns:
        try:
            cur.execute(f"ALTER TABLE users ADD COLUMN {column}")
            conn.commit()
            print(f"ADDED users.{column}")
        except Exception as e:
            conn.commit()
            print(f"SKIPPED users.{column}: {type(e).__name__}")

    conn.close()

def create_user(
    email: str,
    password: str,
    full_name: str,
    phone: str,
    address_line1: str,
    postal_code: str,
    city: str,
    country: str,
    customer_type: str = "private",
    company_name: str = "",
    vat_number: str = "",
):
    ensure_user_profile_columns()
    conn = get_connection()
    cur = conn.cursor()

    normalized_customer_type = (customer_type or "private").strip().lower()
    if normalized_customer_type not in {"private", "company"}:
        normalized_customer_type = "private"

    password_hash = generate_password_hash(password)

    cur.execute(
        """
        INSERT INTO users (
            email,
            password_hash,
            full_name,
            phone,
            address_line1,
            postal_code,
            city,
            country,
            customer_type,
            company_name,
            vat_number,
            is_admin,
            account_type,
            subscription_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'basic', 'inactive')
        """,
        (
            (email or "").lower().strip(),
            password_hash,
            (full_name or "").strip(),
            (phone or "").strip(),
            (address_line1 or "").strip(),
            (postal_code or "").strip(),
            (city or "").strip(),
            (country or "").strip(),
            normalized_customer_type,
            (company_name or "").strip(),
            (vat_number or "").strip(),
        )
    )

    conn.commit()
    conn.close()


def update_user_password(user_id: int, new_password: str):
    conn = get_connection()
    cur = conn.cursor()

    password_hash = generate_password_hash(new_password)
    cur.execute("""
        UPDATE users
        SET password_hash = ?
        WHERE id = ?
    """, (password_hash, user_id))

    conn.commit()
    conn.close()


def make_user_admin(email: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "UPDATE users SET is_admin = 1 WHERE lower(email) = ?",
        ((email or "").lower().strip(),)
    )

    conn.commit()
    conn.close()


def set_user_admin_by_id(user_id: int, is_admin: bool):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET is_admin = ?
        WHERE id = ?
    """, (1 if is_admin else 0, user_id))

    conn.commit()
    conn.close()


def set_user_account_type(user_id: int, account_type: str):
    normalized = (account_type or "basic").strip().lower()
    if normalized not in {"basic", "test"}:
        normalized = "basic"

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET account_type = ?
        WHERE id = ?
    """, (normalized, user_id))

    conn.commit()
    conn.close()


def set_user_subscription(
    user_id: int,
    subscription_status: str,
    subscription_started_at=None,
    subscription_expires_at=None,
):
    normalized = (subscription_status or "inactive").strip().lower()
    if normalized not in {"inactive", "active", "cancelled", "past_due"}:
        normalized = "inactive"

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET subscription_status = ?,
            subscription_started_at = ?,
            subscription_expires_at = ?
        WHERE id = ?
    """, (
        normalized,
        subscription_started_at,
        subscription_expires_at,
        user_id,
    ))

    conn.commit()
    conn.close()


def can_user_access_base_system(user) -> bool:
    if not user:
        return False

    if user["is_admin"] == 1:
        return True

    account_type = (user["account_type"] or "basic").strip().lower()
    subscription_status = (user["subscription_status"] or "inactive").strip().lower()

    if account_type == "test":
        return True

    if account_type == "basic" and subscription_status == "active":
        return True

    return False


def can_user_access_paid_features(user) -> bool:
    return can_user_access_base_system(user)


def can_user_view_repair_guides(user) -> bool:
    if not user:
        return False

    if user["is_admin"] == 1:
        return True

    account_type = (user["account_type"] or "").strip().lower() if "account_type" in user.keys() else ""
    subscription_status = (user["subscription_status"] or "").strip().lower() if "subscription_status" in user.keys() else ""

    if account_type == "test":
        return True

    if subscription_status == "active":
        return True

    return False


def delete_user_by_id(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM solution_feedback WHERE user_id = ?", (user_id,))

    cur.execute("""
        UPDATE suggested_fault_code_updates
        SET reviewed_by_user_id = NULL
        WHERE reviewed_by_user_id = ?
    """, (user_id,))

    cur.execute("""
        DELETE FROM suggested_fault_code_updates
        WHERE diagnosis_id IN (
            SELECT id FROM saved_diagnoses WHERE user_id = ?
        )
    """, (user_id,))

    cur.execute("""
        DELETE FROM solution_feedback
        WHERE diagnosis_id IN (
            SELECT id FROM saved_diagnoses WHERE user_id = ?
        )
    """, (user_id,))

    cur.execute("DELETE FROM password_reset_tokens WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM one_time_purchases WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM accounting_entries WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM saved_diagnoses WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM repair_guide_requests WHERE user_id = ?", (user_id,))
    cur.execute("DELETE FROM users WHERE id = ?", (user_id,))

    conn.commit()
    conn.close()


def count_admin_users():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) AS count
        FROM users
        WHERE is_admin = 1
    """)

    row = cur.fetchone()
    conn.close()
    return row["count"] if row else 0


def set_user_online(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET is_online = 1,
            last_active_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (user_id,))

    conn.commit()
    conn.close()


def set_user_offline(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET is_online = 0,
            last_active_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (user_id,))

    conn.commit()
    conn.close()

def get_all_users_with_stats():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            u.id,
            u.email,
            u.full_name,
            u.phone,
            u.address_line1,
            u.postal_code,
            u.city,
            u.country,
            u.customer_type,
            u.company_name,
            u.vat_number,
            u.is_admin,
            u.account_type,
            u.subscription_status,
            u.subscription_started_at,
            u.subscription_expires_at,
            u.created_at,
            u.last_active_at,
            u.is_online,
            COUNT(sd.id) AS diagnosis_count,
            COUNT(
                CASE
                    WHEN sd.requires_resolution_image = 1 THEN 1
                    ELSE NULL
                END
            ) AS ticket_count
        FROM users u
        LEFT JOIN saved_diagnoses sd ON sd.user_id = u.id
        GROUP BY
            u.id,
            u.email,
            u.full_name,
            u.phone,
            u.address_line1,
            u.postal_code,
            u.city,
            u.country,
            u.customer_type,
            u.company_name,
            u.vat_number,
            u.is_admin,
            u.account_type,
            u.subscription_status,
            u.subscription_started_at,
            u.subscription_expires_at,
            u.created_at,
            u.last_active_at,
            u.is_online
        ORDER BY u.created_at DESC
    """)

    rows = cur.fetchall()
    conn.close()
    return rows

    def admin_update_user(
    user_id: int,
    full_name: str,
    phone: str,
    address_line1: str,
    postal_code: str,
    city: str,
    country: str,
    customer_type: str,
    company_name: str,
    vat_number: str,
    account_type: str,
    is_admin: int,
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE users
        SET
            full_name = ?,
            phone = ?,
            address_line1 = ?,
            postal_code = ?,
            city = ?,
            country = ?,
            customer_type = ?,
            company_name = ?,
            vat_number = ?,
            account_type = ?,
            is_admin = ?
        WHERE id = ?
    """, (
        (full_name or "").strip(),
        (phone or "").strip(),
        (address_line1 or "").strip(),
        (postal_code or "").strip(),
        (city or "").strip(),
        (country or "").strip(),
        (customer_type or "private").strip(),
        (company_name or "").strip(),
        (vat_number or "").strip(),
        (account_type or "basic").strip(),
        int(is_admin),
        user_id,
    ))

    conn.commit()
    conn.close()
