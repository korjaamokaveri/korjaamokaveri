import json
from db_init import get_connection


def save_diagnosis(
    user_id: int,
    code: str,
    make: str,
    model: str,
    engine: str,
    symptoms: str,
    result: dict,
    initial_image_path: str | None = None,
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO saved_diagnoses (
            user_id,
            code,
            make,
            model,
            engine,
            symptoms,
            initial_image_path,
            result_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        code.upper().strip(),
        make.strip(),
        model.strip(),
        engine.strip() if engine else "",
        symptoms.strip() if symptoms else "",
        initial_image_path,
        json.dumps(result, ensure_ascii=False),
    ))

    diagnosis_id = cur.lastrowid

    conn.commit()
    conn.close()

    return diagnosis_id


def get_diagnosis_by_id(diagnosis_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM saved_diagnoses
        WHERE id = ?
    """, (diagnosis_id,))

    row = cur.fetchone()
    conn.close()
    return row


def get_diagnosis_admin_detail(diagnosis_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            sd.*,
            u.email AS user_email
        FROM saved_diagnoses sd
        LEFT JOIN users u ON sd.user_id = u.id
        WHERE sd.id = ?
        LIMIT 1
    """, (diagnosis_id,))

    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    try:
        result = json.loads(row["result_json"]) if row["result_json"] else {}
    except Exception:
        result = {}

    cur.execute("""
        SELECT
            SUM(CASE WHEN helpful = 1 THEN 1 ELSE 0 END) AS likes,
            SUM(CASE WHEN helpful = 0 THEN 1 ELSE 0 END) AS dislikes,
            COUNT(*) AS total_votes
        FROM solution_feedback
        WHERE diagnosis_id = ?
    """, (diagnosis_id,))
    feedback_row = cur.fetchone()

    conn.close()

    resolved = row["resolved"] if "resolved" in row.keys() else 0
    requires_resolution_image = row["requires_resolution_image"] if "requires_resolution_image" in row.keys() else 0

    if resolved == 1:
        status = "closed"
    elif result.get("unknown_code") is True:
        status = "unknown"
    elif requires_resolution_image == 1:
        status = "waiting_for_image"
    else:
        status = "open"

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "user_email": row["user_email"] or "tuntematon",
        "code": row["code"],
        "make": row["make"],
        "model": row["model"],
        "engine": row["engine"] or "",
        "symptoms": row["symptoms"] or "",
        "created_at": row["created_at"],
        "resolved": resolved,
        "status": status,
        "requires_resolution_image": requires_resolution_image,
        "unknown_code": result.get("unknown_code", False),
        "title": result.get("title", ""),
        "description": result.get("description", ""),
        "result": result,
        "final_cause": row["final_cause"] if "final_cause" in row.keys() else "",
        "final_fix": row["final_fix"] if "final_fix" in row.keys() else "",
        "feedback_notes": row["feedback_notes"] if "feedback_notes" in row.keys() else "",
        "initial_image_path": row["initial_image_path"] if "initial_image_path" in row.keys() else "",
        "resolution_image_path": row["resolution_image_path"] if "resolution_image_path" in row.keys() else "",
        "closed_at": row["closed_at"] if "closed_at" in row.keys() else "",
        "likes": feedback_row["likes"] if feedback_row and feedback_row["likes"] is not None else 0,
        "dislikes": feedback_row["dislikes"] if feedback_row and feedback_row["dislikes"] is not None else 0,
        "total_votes": feedback_row["total_votes"] if feedback_row and feedback_row["total_votes"] is not None else 0,
    }


def get_history_for_user(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM saved_diagnoses
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()

    items = []
    for row in rows:
        try:
            result = json.loads(row["result_json"]) if row["result_json"] else {}
        except Exception:
            result = {}

        resolved = row["resolved"] if "resolved" in row.keys() else 0
        requires_resolution_image = row["requires_resolution_image"] if "requires_resolution_image" in row.keys() else 0

        if resolved == 1:
            status = "closed"
        elif requires_resolution_image == 1:
            status = "waiting_for_image"
        else:
            status = "open"

        items.append({
            "id": row["id"],
            "user_id": row["user_id"] if "user_id" in row.keys() else user_id,
            "code": row["code"],
            "make": row["make"],
            "model": row["model"],
            "engine": row["engine"] or "",
            "symptoms": row["symptoms"] or "",
            "created_at": row["created_at"],
            "title": result.get("title", ""),
            "description": result.get("description", ""),
            "resolved": resolved,
            "status": status,
            "final_cause": row["final_cause"] if "final_cause" in row.keys() else "",
            "final_fix": row["final_fix"] if "final_fix" in row.keys() else "",
            "notes": row["feedback_notes"] if "feedback_notes" in row.keys() else "",
            "feedback_notes": row["feedback_notes"] if "feedback_notes" in row.keys() else "",
            "resolution_image_path": row["resolution_image_path"] if "resolution_image_path" in row.keys() else "",
            "initial_image_path": row["initial_image_path"] if "initial_image_path" in row.keys() else "",
            "requires_resolution_image": requires_resolution_image,
            "closed_at": row["closed_at"] if "closed_at" in row.keys() else "",
        })

    return items


def close_diagnosis(
    diagnosis_id: int,
    final_cause: str,
    final_fix: str,
    notes: str,
    resolution_image_path: str = None,
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE saved_diagnoses
        SET resolved = 1,
            final_cause = ?,
            final_fix = ?,
            feedback_notes = ?,
            resolution_image_path = COALESCE(?, resolution_image_path),
            requires_resolution_image = 0,
            closed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        final_cause,
        final_fix,
        notes,
        resolution_image_path,
        diagnosis_id,
    ))

    conn.commit()
    conn.close()

    row = get_diagnosis_by_id(diagnosis_id)
    if row:
        try:
            from services.suggestion_service import create_suggestions_from_closed_ticket
            create_suggestions_from_closed_ticket(
                diagnosis_id=diagnosis_id,
                code=row["code"],
                make=row["make"],
                model=row["model"],
                engine=row["engine"] or "",
                symptoms=row["symptoms"] or "",
                final_cause=final_cause,
                final_fix=final_fix,
            )
        except Exception:
            pass


def close_diagnosis_as_admin(
    diagnosis_id: int,
    final_cause: str,
    final_fix: str,
    notes: str = "",
    resolution_image_path: str = None,
):
    close_diagnosis(
        diagnosis_id=diagnosis_id,
        final_cause=final_cause,
        final_fix=final_fix,
        notes=notes,
        resolution_image_path=resolution_image_path,
    )


def close_diagnosis_by_user(
    diagnosis_id: int,
    user_id: int,
    final_cause: str,
    final_fix: str,
    notes: str,
    resolution_image_path: str,
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE saved_diagnoses
        SET resolved = 1,
            final_cause = ?,
            final_fix = ?,
            feedback_notes = ?,
            resolution_image_path = ?,
            requires_resolution_image = 0,
            closed_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND user_id = ?
    """, (
        final_cause,
        final_fix,
        notes,
        resolution_image_path,
        diagnosis_id,
        user_id,
    ))

    conn.commit()
    conn.close()

    row = get_diagnosis_by_id(diagnosis_id)
    if row:
        try:
            from services.suggestion_service import create_suggestions_from_closed_ticket
            create_suggestions_from_closed_ticket(
                diagnosis_id=diagnosis_id,
                code=row["code"],
                make=row["make"],
                model=row["model"],
                engine=row["engine"] or "",
                symptoms=row["symptoms"] or "",
                final_cause=final_cause,
                final_fix=final_fix,
            )
        except Exception:
            pass


def mark_ticket_requires_resolution_image(diagnosis_id: int, required: bool = True):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE saved_diagnoses
        SET requires_resolution_image = ?
        WHERE id = ?
    """, (1 if required else 0, diagnosis_id))

    conn.commit()
    conn.close()


def get_open_diagnoses():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM saved_diagnoses
        WHERE resolved = 0
        ORDER BY created_at DESC
    """)

    rows = cur.fetchall()
    conn.close()

    items = []
    for row in rows:
        try:
            result = json.loads(row["result_json"]) if row["result_json"] else {}
        except Exception:
            result = {}

        items.append({
            "id": row["id"],
            "code": row["code"],
            "make": row["make"],
            "model": row["model"],
            "engine": row["engine"] or "",
            "symptoms": row["symptoms"] or "",
            "created_at": row["created_at"],
            "resolution_image_path": row["resolution_image_path"] if "resolution_image_path" in row.keys() else "",
            "requires_resolution_image": row["requires_resolution_image"] if "requires_resolution_image" in row.keys() else 0,
            "result": result,
        })

    return items


def get_unknown_code_tickets():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM saved_diagnoses
        WHERE resolved = 0
        ORDER BY created_at DESC
    """)

    rows = cur.fetchall()
    conn.close()

    items = []
    for row in rows:
        try:
            result = json.loads(row["result_json"]) if row["result_json"] else {}
        except Exception:
            result = {}

        if result.get("unknown_code") is True:
            items.append({
                "id": row["id"],
                "code": row["code"],
                "make": row["make"],
                "model": row["model"],
                "engine": row["engine"] or "",
                "symptoms": row["symptoms"] or "",
                "created_at": row["created_at"],
                "resolution_image_path": row["resolution_image_path"] if "resolution_image_path" in row.keys() else "",
                "requires_resolution_image": row["requires_resolution_image"] if "requires_resolution_image" in row.keys() else 0,
                "result": result,
            })

    return items


def get_all_diagnoses(search: str = "", status: str = ""):
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT
            sd.*,
            u.email AS user_email,
            SUM(CASE WHEN sf.helpful = 1 THEN 1 ELSE 0 END) AS likes,
            SUM(CASE WHEN sf.helpful = 0 THEN 1 ELSE 0 END) AS dislikes,
            COUNT(sf.id) AS total_votes
        FROM saved_diagnoses sd
        LEFT JOIN users u ON sd.user_id = u.id
        LEFT JOIN solution_feedback sf ON sf.diagnosis_id = sd.id
        WHERE 1=1
    """
    params = []

    search = (search or "").strip()
    status = (status or "").strip()

    if search:
        query += """
            AND (
                lower(sd.code) LIKE ?
                OR lower(sd.make) LIKE ?
                OR lower(sd.model) LIKE ?
                OR lower(coalesce(sd.engine, '')) LIKE ?
                OR lower(coalesce(sd.symptoms, '')) LIKE ?
                OR lower(coalesce(u.email, '')) LIKE ?
                OR lower(coalesce(sd.final_cause, '')) LIKE ?
                OR lower(coalesce(sd.final_fix, '')) LIKE ?
            )
        """
        like_value = f"%{search.lower()}%"
        params.extend([like_value] * 8)

    if status == "open":
        query += " AND coalesce(sd.resolved, 0) = 0"
    elif status == "closed":
        query += " AND coalesce(sd.resolved, 0) = 1"
    elif status == "unknown":
        query += " AND json_extract(sd.result_json, '$.unknown_code') = 1"

    query += """
        GROUP BY
            sd.id,
            u.email
        ORDER BY sd.created_at DESC, sd.id DESC
    """

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    items = []
    for row in rows:
        try:
            result = json.loads(row["result_json"]) if row["result_json"] else {}
        except Exception:
            result = {}

        resolved = row["resolved"] if "resolved" in row.keys() else 0
        requires_resolution_image = row["requires_resolution_image"] if "requires_resolution_image" in row.keys() else 0

        if resolved == 1:
            resolved_status = "closed"
        elif result.get("unknown_code", False):
            resolved_status = "unknown"
        elif requires_resolution_image == 1:
            resolved_status = "waiting_for_image"
        else:
            resolved_status = "open"

        items.append({
            "id": row["id"],
            "user_email": row["user_email"] or "tuntematon",
            "code": row["code"],
            "make": row["make"],
            "model": row["model"],
            "engine": row["engine"] or "",
            "symptoms": row["symptoms"] or "",
            "created_at": row["created_at"],
            "resolved": resolved,
            "status": resolved_status,
            "final_cause": row["final_cause"] if "final_cause" in row.keys() else "",
            "final_fix": row["final_fix"] if "final_fix" in row.keys() else "",
            "feedback_notes": row["feedback_notes"] if "feedback_notes" in row.keys() else "",
            "resolution_image_path": row["resolution_image_path"] if "resolution_image_path" in row.keys() else "",
            "initial_image_path": row["initial_image_path"] if "initial_image_path" in row.keys() else "",
            "requires_resolution_image": requires_resolution_image,
            "unknown_code": result.get("unknown_code", False),
            "title": result.get("title", ""),
            "description": result.get("description", ""),
            "likes": row["likes"] if row["likes"] is not None else 0,
            "dislikes": row["dislikes"] if row["dislikes"] is not None else 0,
            "total_votes": row["total_votes"] if row["total_votes"] is not None else 0,
        })

    return items


def get_learning_data(code: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT final_cause, COUNT(*) as count
        FROM saved_diagnoses
        WHERE code = ?
          AND resolved = 1
          AND final_cause IS NOT NULL
          AND final_cause != ''
        GROUP BY final_cause
        ORDER BY count DESC
    """, (code.upper().strip(),))

    rows = cur.fetchall()
    conn.close()
    return rows


def get_top_solution(code: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT final_cause, COUNT(*) as count
        FROM saved_diagnoses
        WHERE code = ?
          AND resolved = 1
          AND final_cause IS NOT NULL
          AND final_cause != ''
        GROUP BY final_cause
        ORDER BY count DESC
        LIMIT 1
    """, (code.upper().strip(),))

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_fault_code_from_ticket(
    code: str,
    make: str,
    title: str,
    description: str,
    final_cause: str,
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO fault_codes (code, make, title, description, severity, system)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        code.upper().strip(),
        make.strip() if (make or "").strip() else "Yleinen",
        title.strip(),
        description.strip(),
        "medium",
        "engine",
    ))

    fault_code_id = cur.lastrowid

    if final_cause.strip():
        cur.execute("""
            INSERT INTO possible_causes
            (fault_code_id, cause_name, cause_description, probability_score, priority_order)
            VALUES (?, ?, ?, ?, ?)
        """, (
            fault_code_id,
            final_cause.strip(),
            f"Automaattisesti luotu ratkaistusta tiketistä: {final_cause.strip()}",
            0.50,
            1,
        ))

    conn.commit()
    conn.close()

    return fault_code_id


def get_learning_data_for_make_model(code: str, make: str, model: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT sd.final_cause, COUNT(*) as count
        FROM saved_diagnoses sd
        WHERE sd.code = ?
          AND sd.resolved = 1
          AND sd.final_cause IS NOT NULL
          AND sd.final_cause != ''
          AND lower(sd.make) = ?
          AND lower(sd.model) = ?
        GROUP BY sd.final_cause
        ORDER BY count DESC
    """, (code.upper().strip(), make.lower().strip(), model.lower().strip()))

    rows = cur.fetchall()
    conn.close()
    return rows


def get_learning_data_for_make(code: str, make: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT sd.final_cause, COUNT(*) as count
        FROM saved_diagnoses sd
        WHERE sd.code = ?
          AND sd.resolved = 1
          AND sd.final_cause IS NOT NULL
          AND sd.final_cause != ''
          AND lower(sd.make) = ?
        GROUP BY sd.final_cause
        ORDER BY count DESC
    """, (code.upper().strip(), make.lower().strip()))

    rows = cur.fetchall()
    conn.close()
    return rows


def get_top_solution_with_image(code: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            final_cause,
            resolution_image_path,
            COUNT(*) as count
        FROM saved_diagnoses
        WHERE code = ?
          AND resolved = 1
          AND final_cause IS NOT NULL
          AND final_cause != ''
          AND resolution_image_path IS NOT NULL
          AND resolution_image_path != ''
        GROUP BY final_cause, resolution_image_path
        ORDER BY count DESC
        LIMIT 1
    """, (code.upper().strip(),))

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_diagnosis_result(diagnosis_id: int, result: dict):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE saved_diagnoses
        SET result_json = ?
        WHERE id = ?
    """, (
        json.dumps(result, ensure_ascii=False),
        diagnosis_id,
    ))

    conn.commit()
    conn.close()


def count_open_tickets_missing_resolution_image(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) as count
        FROM saved_diagnoses
        WHERE user_id = ?
          AND resolved = 0
          AND (
              resolution_image_path IS NULL
              OR resolution_image_path = ''
          )
    """, (user_id,))

    row = cur.fetchone()
    conn.close()
    return row["count"] if row else 0
    
def get_user_feedback_for_diagnosis(user_id: int, diagnosis_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM solution_feedback
        WHERE user_id = ?
          AND diagnosis_id = ?
        LIMIT 1
    """, (user_id, diagnosis_id))

    row = cur.fetchone()
    conn.close()
    return row

def save_solution_feedback(
    user_id: int | None,
    diagnosis_id: int | None,
    fault_code: str,
    title: str,
    description: str,
    vehicle: str,
    helpful: bool,
):
    conn = get_connection()
    cur = conn.cursor()

    normalized_fault_code = (fault_code or "").upper().strip()
    normalized_title = (title or "").strip()
    normalized_description = (description or "").strip()
    normalized_vehicle = (vehicle or "").strip()
    helpful_value = 1 if helpful else 0

    if user_id is not None and diagnosis_id is not None:
        cur.execute("""
            SELECT id
            FROM solution_feedback
            WHERE user_id = ?
              AND diagnosis_id = ?
            LIMIT 1
        """, (user_id, diagnosis_id))

        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE solution_feedback
                SET fault_code = ?,
                    title = ?,
                    description = ?,
                    vehicle = ?,
                    helpful = ?,
                    created_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                normalized_fault_code,
                normalized_title,
                normalized_description,
                normalized_vehicle,
                helpful_value,
                existing["id"],
            ))
        else:
            cur.execute("""
                INSERT INTO solution_feedback (
                    user_id,
                    diagnosis_id,
                    fault_code,
                    title,
                    description,
                    vehicle,
                    helpful
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                diagnosis_id,
                normalized_fault_code,
                normalized_title,
                normalized_description,
                normalized_vehicle,
                helpful_value,
            ))
    else:
        cur.execute("""
            INSERT INTO solution_feedback (
                user_id,
                diagnosis_id,
                fault_code,
                title,
                description,
                vehicle,
                helpful
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            diagnosis_id,
            normalized_fault_code,
            normalized_title,
            normalized_description,
            normalized_vehicle,
            helpful_value,
        ))

    conn.commit()
    conn.close()

def get_popular_repairs(limit: int = 20):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            fault_code,
            title,
            description,
            SUM(CASE WHEN helpful = 1 THEN 1 ELSE 0 END) AS likes,
            SUM(CASE WHEN helpful = 0 THEN 1 ELSE 0 END) AS dislikes,
            COUNT(*) AS total_votes
        FROM solution_feedback
        GROUP BY fault_code, title, description
        HAVING COUNT(*) > 0
        ORDER BY likes DESC, total_votes DESC, fault_code ASC
        LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return [dict(r) for r in rows]