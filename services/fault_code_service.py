from db_init import get_connection


def normalize_make_for_storage(make: str) -> str:
    value = (make or "").strip()
    return value if value else "Yleinen"


def normalize_code(code: str) -> str:
    return (code or "").upper().strip()


def system_from_code(code: str) -> str:
    code = normalize_code(code)

    if code.startswith("P"):
        return "powertrain"
    if code.startswith("B"):
        return "body"
    if code.startswith("C"):
        return "chassis"
    if code.startswith("U"):
        return "network"

    return "engine"


def find_fault_code(code: str):
    return find_fault_code_for_make(code, "Yleinen")


def find_fault_code_for_make(code: str, make: str):
    conn = get_connection()
    cur = conn.cursor()

    normalized_code = normalize_code(code)
    normalized_make = normalize_make_for_storage(make)

    cur.execute("""
        SELECT *
        FROM fault_codes
        WHERE upper(trim(code)) = upper(trim(?))
        ORDER BY
            CASE
                WHEN lower(trim(coalesce(make, ''))) = lower(trim(?)) THEN 0
                WHEN lower(trim(coalesce(make, ''))) = 'yleinen' THEN 1
                WHEN trim(coalesce(make, '')) = '' THEN 2
                ELSE 3
            END
        LIMIT 1
    """, (normalized_code, normalized_make))

    row = cur.fetchone()
    conn.close()
    return row


def get_all_fault_codes():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            code,
            make,
            title,
            description,
            problem_symptoms,
            mil_status,
            fail_safe_function,
            priority,
            sae_code
        FROM fault_codes
        ORDER BY
            CASE
                WHEN make IS NULL OR TRIM(make) = '' THEN 'Yleinen'
                ELSE make
            END ASC,
            code ASC
    """)

    rows = cur.fetchall()
    conn.close()
    return rows


def get_fault_code_by_id(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            code,
            make,
            title,
            description,
            problem_symptoms,
            mil_status,
            fail_safe_function,
            priority,
            sae_code
        FROM fault_codes
        WHERE id = ?
    """, (fault_code_id,))

    fault_code = cur.fetchone()

    if not fault_code:
        conn.close()
        return None

    cur.execute("""
        SELECT cause_name
        FROM possible_causes
        WHERE fault_code_id = ?
        ORDER BY priority_order ASC
    """, (fault_code_id,))
    causes = [row["cause_name"] for row in cur.fetchall()]

    cur.execute("""
        SELECT step_title
        FROM test_steps
        WHERE fault_code_id = ?
        ORDER BY step_order ASC
    """, (fault_code_id,))
    steps = [row["step_title"] for row in cur.fetchall()]

    conn.close()

    return {
        "id": fault_code["id"],
        "code": fault_code["code"],
        "make": normalize_make_for_storage(fault_code["make"]),
        "title": fault_code["title"],
        "description": fault_code["description"],
        "problem_symptoms": fault_code["problem_symptoms"] or "",
        "mil_status": fault_code["mil_status"] or "",
        "fail_safe_function": fault_code["fail_safe_function"] or "",
        "priority": fault_code["priority"] or "",
        "sae_code": fault_code["sae_code"] or "",
        "causes_text": "\n".join(causes),
        "steps_text": "\n".join(steps),
    }


def create_fault_code_with_details(
    code: str,
    make: str,
    title: str,
    description: str,
    causes_text: str,
    steps_text: str,
    problem_symptoms: str = "",
    mil_status: str = "",
    fail_safe_function: str = "",
    priority: str = "",
    sae_code: str = "",
):
    normalized_code = normalize_code(code)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO fault_codes (
            code,
            make,
            title,
            description,
            severity,
            system,
            problem_symptoms,
            mil_status,
            fail_safe_function,
            priority,
            sae_code
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        normalized_code,
        normalize_make_for_storage(make),
        (title or "").strip(),
        (description or "").strip(),
        "medium",
        system_from_code(normalized_code),
        (problem_symptoms or "").strip(),
        (mil_status or "").strip(),
        (fail_safe_function or "").strip(),
        (priority or "").strip(),
        (sae_code or "").strip(),
    ))

    fault_code_id = cur.lastrowid

    causes = [line.strip() for line in (causes_text or "").splitlines() if line.strip()]
    for idx, cause in enumerate(causes, start=1):
        cur.execute("""
            INSERT INTO possible_causes (
                fault_code_id,
                cause_name,
                cause_description,
                probability_score,
                priority_order
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            fault_code_id,
            cause,
            f"Adminin lisäämä mahdollinen syy: {cause}",
            max(0.1, round(0.5 - (idx - 1) * 0.1, 2)),
            idx,
        ))

    steps = [line.strip() for line in (steps_text or "").splitlines() if line.strip()]
    for idx, step in enumerate(steps, start=1):
        cur.execute("""
            INSERT INTO test_steps (
                fault_code_id,
                step_order,
                step_title,
                step_description,
                required_tools
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            fault_code_id,
            idx,
            step,
            step,
            "ei määritelty",
        ))

    conn.commit()
    conn.close()

    return fault_code_id


def update_fault_code_with_details(
    fault_code_id: int,
    code: str,
    make: str,
    title: str,
    description: str,
    causes_text: str,
    steps_text: str,
    problem_symptoms: str = "",
    mil_status: str = "",
    fail_safe_function: str = "",
    priority: str = "",
    sae_code: str = "",
):
    normalized_code = normalize_code(code)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE fault_codes
        SET
            code = ?,
            make = ?,
            title = ?,
            description = ?,
            severity = ?,
            system = ?,
            problem_symptoms = ?,
            mil_status = ?,
            fail_safe_function = ?,
            priority = ?,
            sae_code = ?
        WHERE id = ?
    """, (
        normalized_code,
        normalize_make_for_storage(make),
        (title or "").strip(),
        (description or "").strip(),
        "medium",
        system_from_code(normalized_code),
        (problem_symptoms or "").strip(),
        (mil_status or "").strip(),
        (fail_safe_function or "").strip(),
        (priority or "").strip(),
        (sae_code or "").strip(),
        fault_code_id,
    ))

    cur.execute("DELETE FROM possible_causes WHERE fault_code_id = ?", (fault_code_id,))
    cur.execute("DELETE FROM test_steps WHERE fault_code_id = ?", (fault_code_id,))

    causes = [line.strip() for line in (causes_text or "").splitlines() if line.strip()]
    for idx, cause in enumerate(causes, start=1):
        cur.execute("""
            INSERT INTO possible_causes (
                fault_code_id,
                cause_name,
                cause_description,
                probability_score,
                priority_order
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            fault_code_id,
            cause,
            f"Adminin päivittämä mahdollinen syy: {cause}",
            max(0.1, round(0.5 - (idx - 1) * 0.1, 2)),
            idx,
        ))

    steps = [line.strip() for line in (steps_text or "").splitlines() if line.strip()]
    for idx, step in enumerate(steps, start=1):
        cur.execute("""
            INSERT INTO test_steps (
                fault_code_id,
                step_order,
                step_title,
                step_description,
                required_tools
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            fault_code_id,
            idx,
            step,
            step,
            "ei määritelty",
        ))

    conn.commit()
    conn.close()


def delete_fault_code(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM possible_causes WHERE fault_code_id = ?", (fault_code_id,))
    cur.execute("DELETE FROM symptom_matches WHERE fault_code_id = ?", (fault_code_id,))
    cur.execute("DELETE FROM test_steps WHERE fault_code_id = ?", (fault_code_id,))
    cur.execute("DELETE FROM vehicle_rules WHERE fault_code_id = ?", (fault_code_id,))
    cur.execute("DELETE FROM suggested_fault_code_updates WHERE fault_code_id = ?", (fault_code_id,))
    cur.execute("DELETE FROM fault_codes WHERE id = ?", (fault_code_id,))

    conn.commit()
    conn.close()