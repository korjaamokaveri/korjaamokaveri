import json
import re

from db_init import get_connection
from services.fault_code_service import find_fault_code_for_make
from services.dtc_enrichment_service import build_dtc_enrichment

def normalize_text(value: str) -> str:
    return (value or "").strip().lower()


def split_symptom_candidates(symptoms: str):
    parts = re.split(r"[\n,.;]+", symptoms or "")
    cleaned = []

    for part in parts:
        value = " ".join(part.strip().split())
        lowered = value.lower()

        if len(value) < 4:
            continue

        if len(value) > 80:
            continue

        if lowered in {
            "ei kuvattu",
            "vika",
            "ongelma",
            "auto",
            "moottori",
            "korjattu",
        }:
            continue

        cleaned.append(value)

    unique = []
    seen = set()
    for item in cleaned:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique[:5]


def get_fault_code_full_by_code_make(code: str, make: str):
    fault = find_fault_code_for_make(code, make)
    if not fault:
        return None
    return fault


def get_existing_possible_causes(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT cause_name
        FROM possible_causes
        WHERE fault_code_id = ?
    """, (fault_code_id,))
    rows = cur.fetchall()
    conn.close()
    return [normalize_text(r["cause_name"]) for r in rows]


def get_existing_symptom_keywords(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT keyword
        FROM symptom_matches
        WHERE fault_code_id = ?
    """, (fault_code_id,))
    rows = cur.fetchall()
    conn.close()
    return [normalize_text(r["keyword"]) for r in rows]


def get_existing_vehicle_rule_notes(fault_code_id: int, make: str, model: str, engine: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT rule_note
        FROM vehicle_rules
        WHERE fault_code_id = ?
          AND lower(coalesce(make, '')) = ?
          AND lower(coalesce(model, '')) = ?
          AND lower(coalesce(engine, '')) = ?
    """, (
        fault_code_id,
        normalize_text(make),
        normalize_text(model),
        normalize_text(engine),
    ))
    rows = cur.fetchall()
    conn.close()
    return [normalize_text(r["rule_note"]) for r in rows]


def suggestion_exists(fault_code_id: int, suggestion_type: str, payload: dict):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, payload_json
        FROM suggested_fault_code_updates
        WHERE fault_code_id = ?
          AND suggestion_type = ?
          AND status = 'pending'
    """, (fault_code_id, suggestion_type))
    rows = cur.fetchall()
    conn.close()

    normalized_new = json.dumps(payload, ensure_ascii=False, sort_keys=True)

    for row in rows:
        try:
            existing = json.dumps(json.loads(row["payload_json"]), ensure_ascii=False, sort_keys=True)
        except Exception:
            existing = row["payload_json"] or ""

        if existing == normalized_new:
            return True

    return False


def create_suggestion(
    diagnosis_id: int | None,
    fault_code_id: int,
    suggestion_type: str,
    payload: dict,
    source_summary: str,
):
    if suggestion_exists(fault_code_id, suggestion_type, payload):
        return None

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO suggested_fault_code_updates (
            diagnosis_id,
            fault_code_id,
            suggestion_type,
            payload_json,
            source_summary,
            status
        )
        VALUES (?, ?, ?, ?, ?, 'pending')
    """, (
        diagnosis_id,
        fault_code_id,
        suggestion_type,
        json.dumps(payload, ensure_ascii=False),
        source_summary,
    ))

    suggestion_id = cur.lastrowid
    conn.commit()
    conn.close()
    return suggestion_id


def create_suggestions_from_closed_ticket(
    diagnosis_id: int,
    code: str,
    make: str,
    model: str,
    engine: str,
    symptoms: str,
    final_cause: str,
    final_fix: str,
):
    fault = get_fault_code_full_by_code_make(code, make)
    if not fault:
        return []

    fault_code_id = fault["id"]
    created_ids = []

    existing_causes = get_existing_possible_causes(fault_code_id)
    existing_keywords = get_existing_symptom_keywords(fault_code_id)
    existing_rule_notes = get_existing_vehicle_rule_notes(fault_code_id, make, model, engine)

    final_cause_clean = (final_cause or "").strip()
    final_fix_clean = (final_fix or "").strip()

    if final_cause_clean:
        normalized_cause = normalize_text(final_cause_clean)
        if normalized_cause and normalized_cause not in existing_causes:
            suggestion_id = create_suggestion(
                diagnosis_id=diagnosis_id,
                fault_code_id=fault_code_id,
                suggestion_type="possible_cause",
                payload={
                    "cause_name": final_cause_clean,
                    "cause_description": f"Käyttäjän ratkaistusta tiketistä havaittu mahdollinen syy: {final_cause_clean}",
                    "probability_score": 0.25,
                },
                source_summary=f"Uusi mahdollinen syy tiketistä #{diagnosis_id}: {final_cause_clean}",
            )
            if suggestion_id:
                created_ids.append(suggestion_id)

    symptom_candidates = split_symptom_candidates(symptoms)
    for symptom in symptom_candidates:
        normalized_symptom = normalize_text(symptom)
        if normalized_symptom and normalized_symptom not in existing_keywords:
            note_text = final_cause_clean or final_fix_clean or "Käyttäjän ratkaisusta havaittu uusi oireyhteys."
            suggestion_id = create_suggestion(
                diagnosis_id=diagnosis_id,
                fault_code_id=fault_code_id,
                suggestion_type="symptom_match",
                payload={
                    "keyword": symptom,
                    "note": f"Tiketissä #{diagnosis_id} oire '{symptom}' liittyi ratkaisuun: {note_text}",
                    "weight": 1.0,
                },
                source_summary=f"Uusi oirehavainto tiketistä #{diagnosis_id}: {symptom}",
            )
            if suggestion_id:
                created_ids.append(suggestion_id)

    if final_cause_clean and make and model:
        suggested_note = f"Tässä ajoneuvossa {make} {model} {engine or ''} ratkaistu syy oli: {final_cause_clean}".strip()
        if normalize_text(suggested_note) not in existing_rule_notes:
            suggestion_id = create_suggestion(
                diagnosis_id=diagnosis_id,
                fault_code_id=fault_code_id,
                suggestion_type="vehicle_rule",
                payload={
                    "make": make,
                    "model": model,
                    "engine": engine or "",
                    "year_from": None,
                    "year_to": None,
                    "rule_note": suggested_note,
                    "extra_probability_boost": 0.10,
                },
                source_summary=f"Ajoneuvokohtainen sääntöehdotus tiketistä #{diagnosis_id}: {make} {model} / {final_cause_clean}",
            )
            if suggestion_id:
                created_ids.append(suggestion_id)

    return created_ids


def list_suggested_updates(status: str = "pending"):
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT
            s.*,
            f.code AS fault_code,
            f.make AS fault_make,
            f.title AS fault_title,
            sd.make AS diagnosis_make,
            sd.model AS diagnosis_model,
            sd.engine AS diagnosis_engine,
            sd.symptoms AS diagnosis_symptoms,
            sd.final_cause AS diagnosis_final_cause,
            sd.final_fix AS diagnosis_final_fix,
            u.email AS reviewed_by_email
        FROM suggested_fault_code_updates s
        JOIN fault_codes f ON s.fault_code_id = f.id
        LEFT JOIN saved_diagnoses sd ON s.diagnosis_id = sd.id
        LEFT JOIN users u ON s.reviewed_by_user_id = u.id
        WHERE 1=1
    """
    params = []

    if status:
        query += " AND s.status = ?"
        params.append(status)

    query += " ORDER BY s.created_at DESC, s.id DESC"

    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()

    items = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"]) if row["payload_json"] else {}
        except Exception:
            payload = {}

        items.append({
            "id": row["id"],
            "diagnosis_id": row["diagnosis_id"],
            "fault_code_id": row["fault_code_id"],
            "fault_code": row["fault_code"],
            "fault_make": row["fault_make"],
            "fault_title": row["fault_title"],
            "suggestion_type": row["suggestion_type"],
            "payload": payload,
            "source_summary": row["source_summary"] or "",
            "status": row["status"],
            "admin_note": row["admin_note"] or "",
            "created_at": row["created_at"],
            "reviewed_at": row["reviewed_at"],
            "reviewed_by_email": row["reviewed_by_email"] or "",
            "diagnosis_make": row["diagnosis_make"] or "",
            "diagnosis_model": row["diagnosis_model"] or "",
            "diagnosis_engine": row["diagnosis_engine"] or "",
            "diagnosis_symptoms": row["diagnosis_symptoms"] or "",
            "diagnosis_final_cause": row["diagnosis_final_cause"] or "",
            "diagnosis_final_fix": row["diagnosis_final_fix"] or "",
        })

    return items


def get_suggested_update_by_id(suggestion_id: int):
    items = list_suggested_updates(status="")
    for item in items:
        if item["id"] == suggestion_id:
            return item
    return None


def get_next_priority_order(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(MAX(priority_order), 0) AS max_priority
        FROM possible_causes
        WHERE fault_code_id = ?
    """, (fault_code_id,))
    row = cur.fetchone()
    conn.close()
    return (row["max_priority"] if row else 0) + 1


def approve_suggested_update(suggestion_id: int, reviewed_by_user_id: int, admin_note: str = ""):
    suggestion = get_suggested_update_by_id(suggestion_id)
    if not suggestion:
        return False, "Ehdotusta ei löytynyt."

    if suggestion["status"] != "pending":
        return False, "Ehdotus on jo käsitelty."

    payload = suggestion["payload"]
    fault_code_id = suggestion["fault_code_id"]
    suggestion_type = suggestion["suggestion_type"]

    conn = get_connection()
    cur = conn.cursor()

    try:
        if suggestion_type == "possible_cause":
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
                payload.get("cause_name", "").strip(),
                payload.get("cause_description", "").strip(),
                float(payload.get("probability_score", 0.25)),
                get_next_priority_order(fault_code_id),
            ))

        elif suggestion_type == "symptom_match":
            cur.execute("""
                INSERT INTO symptom_matches (
                    fault_code_id,
                    keyword,
                    note,
                    weight
                )
                VALUES (?, ?, ?, ?)
            """, (
                fault_code_id,
                payload.get("keyword", "").strip(),
                payload.get("note", "").strip(),
                float(payload.get("weight", 1.0)),
            ))

        elif suggestion_type == "vehicle_rule":
            cur.execute("""
                INSERT INTO vehicle_rules (
                    fault_code_id,
                    make,
                    model,
                    engine,
                    year_from,
                    year_to,
                    rule_note,
                    extra_probability_boost
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fault_code_id,
                payload.get("make", "").strip(),
                payload.get("model", "").strip(),
                payload.get("engine", "").strip(),
                payload.get("year_from"),
                payload.get("year_to"),
                payload.get("rule_note", "").strip(),
                float(payload.get("extra_probability_boost", 0.10)),
            ))
        else:
            conn.close()
            return False, "Tuntematon ehdotustyyppi."

        cur.execute("""
            UPDATE suggested_fault_code_updates
            SET status = 'approved',
                admin_note = ?,
                reviewed_by_user_id = ?,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (
            admin_note.strip(),
            reviewed_by_user_id,
            suggestion_id,
        ))

        conn.commit()
        conn.close()
        return True, "Ehdotus hyväksytty."

    except Exception as e:
        conn.rollback()
        conn.close()
        return False, f"Hyväksyntä epäonnistui: {e}"


def reject_suggested_update(suggestion_id: int, reviewed_by_user_id: int, admin_note: str = ""):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE suggested_fault_code_updates
        SET status = 'rejected',
            admin_note = ?,
            reviewed_by_user_id = ?,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
          AND status = 'pending'
    """, (
        admin_note.strip(),
        reviewed_by_user_id,
        suggestion_id,
    ))

    changed = cur.rowcount
    conn.commit()
    conn.close()

    if changed == 0:
        return False, "Ehdotusta ei löytynyt tai se on jo käsitelty."

    return True, "Ehdotus hylätty."
def create_ai_enrichment_suggestions(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM fault_codes
        WHERE id = ?
    """, (fault_code_id,))

    fault = cur.fetchone()
    conn.close()

    if not fault:
        return []

    enrichment = build_dtc_enrichment(fault)
    created_ids = []

    if enrichment.get("problem_symptoms"):
        suggestion_id = create_suggestion(
            diagnosis_id=None,
            fault_code_id=fault_code_id,
            suggestion_type="fault_code_text_update",
            payload={
                "problem_symptoms": enrichment["problem_symptoms"],
            },
            source_summary=enrichment["admin_note"],
        )
        if suggestion_id:
            created_ids.append(suggestion_id)

    for cause in enrichment.get("causes", "").splitlines():
        cause = cause.strip()
        if cause:
            suggestion_id = create_suggestion(
                diagnosis_id=None,
                fault_code_id=fault_code_id,
                suggestion_type="possible_cause",
                payload={
                    "cause_name": cause,
                    "cause_description": f"Paikallisen AI-rikastuksen ehdottama mahdollinen syy: {cause}",
                    "probability_score": 0.25,
                },
                source_summary=enrichment["admin_note"],
            )
            if suggestion_id:
                created_ids.append(suggestion_id)

    for step in enrichment.get("steps", "").splitlines():
        step = step.strip()
        if step:
            suggestion_id = create_suggestion(
                diagnosis_id=None,
                fault_code_id=fault_code_id,
                suggestion_type="test_step",
                payload={
                    "step_title": step,
                    "step_description": step,
                    "required_tools": "vikakoodinlukija / yleismittari",
                },
                source_summary=enrichment["admin_note"],
            )
            if suggestion_id:
                created_ids.append(suggestion_id)

    return created_ids