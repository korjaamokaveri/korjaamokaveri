from db_init import get_connection
from services.fault_code_service import find_fault_code_for_make
from services.ticket_service import (
    get_learning_data,
    get_learning_data_for_make,
    get_learning_data_for_make_model,
    get_top_solution,
    get_top_solution_with_image,
)


def normalize_text(value: str) -> str:
    return (value or "").strip().lower()


def get_causes(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM possible_causes
        WHERE fault_code_id = ?
        ORDER BY priority_order ASC, probability_score DESC
        """,
        (fault_code_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_symptom_matches(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM symptom_matches
        WHERE fault_code_id = ?
        """,
        (fault_code_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_test_steps(fault_code_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM test_steps
        WHERE fault_code_id = ?
        ORDER BY step_order ASC
        """,
        (fault_code_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_vehicle_rules(fault_code_id: int, make: str, model: str, engine: str = ""):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM vehicle_rules
        WHERE fault_code_id = ?
          AND lower(make) = ?
          AND lower(model) = ?
        """,
        (fault_code_id, normalize_text(make), normalize_text(model)),
    )
    rows = cur.fetchall()
    conn.close()

    rules = [dict(r) for r in rows]

    if engine:
        engine_norm = normalize_text(engine)
        exact = [r for r in rules if normalize_text(r.get("engine") or "") == engine_norm]
        if exact:
            return exact

    return rules


def apply_symptom_boosts(causes, symptoms_text, symptom_matches):
    symptoms_text = normalize_text(symptoms_text)
    notes = []
    matched_keywords = []

    for symptom in symptom_matches:
        keyword = normalize_text(symptom["keyword"])

        if keyword and keyword in symptoms_text:
            matched_keywords.append(keyword)
            if symptom.get("note"):
                notes.append(symptom["note"])

            if keyword in ["nykii", "tärisee"]:
                for cause in causes:
                    if cause["cause_name"] in ["sytytyspuola", "sytytystulppa"]:
                        cause["probability_score"] += 0.05

            if keyword == "tyhjäkäynti":
                for cause in causes:
                    if cause["cause_name"] in ["imuvuoto", "alipaineletku"]:
                        cause["probability_score"] += 0.05

    return causes, notes, matched_keywords


def apply_vehicle_rules(causes, vehicle_rules):
    if not vehicle_rules:
        return causes, []

    vehicle_notes = []

    for rule in vehicle_rules:
        note = rule.get("rule_note")
        boost = rule.get("extra_probability_boost", 0) or 0

        if note:
            vehicle_notes.append(note)

        if boost:
            for cause in causes:
                cause["probability_score"] += boost

    return causes, vehicle_notes


def diagnose(code: str, make: str, model: str, symptoms: str, engine: str = ""):
    fault = find_fault_code_for_make(code, make)

    if not fault:
        return {
            "success": False,
            "unknown_code": True,
            "fault_code": code.upper().strip(),
            "message": "Vikakoodia ei löytynyt järjestelmästä. Tiketti on vastaanotettu ja vastaamme sinulle 24 tunnin kuluessa. Löydät vastauksen tikettihistoriasta.",
        }

    fault_id = fault["id"]
    causes = get_causes(fault_id)
    symptom_matches = get_symptom_matches(fault_id)
    test_steps = get_test_steps(fault_id)
    vehicle_rules = get_vehicle_rules(fault_id, make, model, engine)

    causes, symptom_notes, matched_keywords = apply_symptom_boosts(
        causes, symptoms, symptom_matches
    )
    causes, vehicle_notes = apply_vehicle_rules(causes, vehicle_rules)

    learning_make_model = get_learning_data_for_make_model(code, make, model)
    for row in learning_make_model:
        learned_cause = (row["final_cause"] or "").lower()
        boost = min(row["count"] * 0.10, 0.40)

        for cause in causes:
            if learned_cause and learned_cause in cause["cause_name"].lower():
                cause["probability_score"] += boost

    learning_make = get_learning_data_for_make(code, make)
    for row in learning_make:
        learned_cause = (row["final_cause"] or "").lower()
        boost = min(row["count"] * 0.07, 0.30)

        for cause in causes:
            if learned_cause and learned_cause in cause["cause_name"].lower():
                cause["probability_score"] += boost

    learning_global = get_learning_data(code)
    for row in learning_global:
        learned_cause = (row["final_cause"] or "").lower()
        boost = min(row["count"] * 0.05, 0.20)

        for cause in causes:
            if learned_cause and learned_cause in cause["cause_name"].lower():
                cause["probability_score"] += boost

    causes = sorted(causes, key=lambda x: x["probability_score"], reverse=True)
    top_solution = get_top_solution(code)
    top_solution_with_image = get_top_solution_with_image(code)

    return {
        "success": True,
        "unknown_code": False,
        "fault_code": fault["code"],
        "title": fault["title"],
        "description": fault["description"],
        "problem_symptoms": fault["problem_symptoms"] or "",
        "mil_status": fault["mil_status"] or "",
        "fail_safe_function": fault["fail_safe_function"] or "",
        "priority": fault["priority"] or "",
        "sae_code": fault["sae_code"] or "",
        "vehicle": {
            "make": make,
            "model": model,
            "engine": engine,
        },
        "matched_symptoms": matched_keywords,
        "symptom_notes": symptom_notes,
        "vehicle_notes": vehicle_notes,
        "possible_causes": [
            {
                "name": c["cause_name"],
                "description": c["cause_description"],
                "score": round(c["probability_score"], 2),
            }
            for c in causes
        ],
        "test_steps": [
            {
                "order": s["step_order"],
                "title": s["step_title"],
                "description": s["step_description"],
                "tools": s["required_tools"],
            }
            for s in test_steps
        ],
        "top_solution": top_solution,
        "top_solution_with_image": top_solution_with_image,
    }