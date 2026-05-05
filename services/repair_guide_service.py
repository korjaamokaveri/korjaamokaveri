import re
from collections import OrderedDict

from db_init import get_connection


def clean_text(value):
    return (value or "").strip()


def normalize_make(value):
    return clean_text(value).title()


def normalize_part_name(value):
    return clean_text(value).lower()


def normalize_vehicle_input(value):
    return clean_text(value).upper().replace(" ", "").replace("-", "")


def detect_input_type(value: str):
    normalized = normalize_vehicle_input(value)

    if not normalized:
        return "unknown", None

    if len(normalized) == 17 and not re.search(r"[IOQ]", normalized):
        return "vin", normalized[:5]

    if re.match(r"^[A-ZÅÄÖ]{2,3}[0-9]{1,3}$", normalized):
        return "reg", None

    return "unknown", None


def create_request(user_id, make, vehicle_input, part_name, note):
    make = normalize_make(make)
    vehicle_input = clean_text(vehicle_input)
    part_name = normalize_part_name(part_name)
    note = clean_text(note)

    input_type, vin_prefix = detect_input_type(vehicle_input)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO repair_guide_requests (
            user_id, make, vehicle_input, input_type, vin_prefix, part_name, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, make, vehicle_input, input_type, vin_prefix, part_name, note))

    conn.commit()
    conn.close()


def get_user_requests(user_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM repair_guide_requests
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()
    return rows


def get_all_requests():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT rgr.*, u.email AS user_email
        FROM repair_guide_requests rgr
        LEFT JOIN users u ON rgr.user_id = u.id
        ORDER BY rgr.created_at DESC, rgr.id DESC
    """)

    rows = cur.fetchall()
    conn.close()
    return rows


def get_request_by_id(request_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT rgr.*, u.email AS user_email
        FROM repair_guide_requests rgr
        LEFT JOIN users u ON rgr.user_id = u.id
        WHERE rgr.id = ?
    """, (request_id,))

    row = cur.fetchone()
    conn.close()
    return row


def create_repair_guide_from_request(
    request_id: int,
    created_by_user_id: int,
    make: str,
    part_name: str,
    vin_prefix: str,
    title: str,
    steps: str,
    tools: str,
    notes: str,
):
    make = normalize_make(make)
    part_name = normalize_part_name(part_name)
    vin_prefix = normalize_vehicle_input(vin_prefix)[:5] if vin_prefix else ""
    title = clean_text(title)
    steps = clean_text(steps)
    tools = clean_text(tools)
    notes = clean_text(notes)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO repair_guides (
            make, part_name, vin_prefix, title, steps, tools, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (make, part_name, vin_prefix, title, steps, tools, notes))

    guide_id = cur.lastrowid

    cur.execute("""
        UPDATE repair_guide_requests
        SET status = 'completed',
            completed_at = CURRENT_TIMESTAMP,
            guide_id = ?
        WHERE id = ?
    """, (guide_id, request_id))

    conn.commit()
    conn.close()
    return guide_id


def get_all_repair_guides():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM repair_guides
        ORDER BY lower(trim(make)) ASC, lower(trim(part_name)) ASC, created_at DESC, id DESC
    """)

    rows = cur.fetchall()
    conn.close()
    return rows


def group_repair_guides_by_make(items):
    grouped = OrderedDict()

    for row in items:
        make = clean_text(row["make"]) or "Tuntematon"
        grouped.setdefault(make, []).append(row)

    return grouped


def get_repair_guide_by_id(guide_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM repair_guides WHERE id = ?", (guide_id,))

    row = cur.fetchone()
    conn.close()
    return row


def update_repair_guide(
    guide_id: int,
    make: str,
    part_name: str,
    vin_prefix: str,
    title: str,
    steps: str,
    tools: str,
    notes: str,
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE repair_guides
        SET make = ?,
            part_name = ?,
            vin_prefix = ?,
            title = ?,
            steps = ?,
            tools = ?,
            notes = ?
        WHERE id = ?
    """, (
        normalize_make(make),
        normalize_part_name(part_name),
        normalize_vehicle_input(vin_prefix)[:5] if vin_prefix else "",
        clean_text(title),
        clean_text(steps),
        clean_text(tools),
        clean_text(notes),
        guide_id,
    ))

    conn.commit()
    conn.close()


def find_best_guide(make, part_name, vin_prefix=None):
    conn = get_connection()
    cur = conn.cursor()

    make = normalize_make(make)
    part_name = normalize_part_name(part_name)
    vin_prefix = normalize_vehicle_input(vin_prefix)[:5] if vin_prefix else ""

    if vin_prefix:
        cur.execute("""
            SELECT *,
                   100 AS match_score,
                   'make + part + vin_prefix' AS match_reason
            FROM repair_guides
            WHERE lower(trim(make)) = lower(trim(?))
              AND lower(trim(part_name)) = lower(trim(?))
              AND upper(trim(coalesce(vin_prefix, ''))) = upper(trim(?))
            ORDER BY id DESC
            LIMIT 1
        """, (make, part_name, vin_prefix))

        row = cur.fetchone()
        if row:
            conn.close()
            return row

    cur.execute("""
        SELECT *,
               80 AS match_score,
               'make + part' AS match_reason
        FROM repair_guides
        WHERE lower(trim(make)) = lower(trim(?))
          AND lower(trim(part_name)) = lower(trim(?))
        ORDER BY id DESC
        LIMIT 1
    """, (make, part_name))

    row = cur.fetchone()
    conn.close()
    return row