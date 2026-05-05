import os
import time
import json

from flask import render_template, request, redirect, url_for, current_app, jsonify
from werkzeug.utils import secure_filename

from decorators import login_required, get_current_user
from services.ticket_service import (
    get_history_for_user,
    get_diagnosis_by_id,
    close_diagnosis_by_user,
    get_user_feedback_for_diagnosis,
)

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_image_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_resolution_image(file_storage, diagnosis_id: int):
    if not file_storage or not file_storage.filename:
        return None

    if not allowed_image_file(file_storage.filename):
        return None

    filename = secure_filename(file_storage.filename)
    filename = f"user_ticket_{diagnosis_id}_{int(time.time())}_{filename}"

    upload_folder = os.path.join(current_app.static_folder, "uploads", "tickets")
    os.makedirs(upload_folder, exist_ok=True)

    save_path = os.path.join(upload_folder, filename)
    file_storage.save(save_path)

    return f"uploads/tickets/{filename}"


def serialize_history_item(row):
    try:
        result = json.loads(row["result_json"]) if "result_json" in row.keys() and row["result_json"] else {}
    except Exception:
        result = {}

    resolved = row["resolved"] if "resolved" in row.keys() else 0
    requires_resolution_image = row["requires_resolution_image"] if "requires_resolution_image" in row.keys() else 0

    if "status" in row.keys() and row["status"]:
        status = row["status"]
    else:
        if resolved == 1:
            status = "closed"
        elif requires_resolution_image == 1:
            status = "waiting_for_image"
        else:
            status = "open"

    notes = ""
    if "notes" in row.keys() and row["notes"]:
        notes = row["notes"]
    elif "feedback_notes" in row.keys() and row["feedback_notes"]:
        notes = row["feedback_notes"]

    return {
        "id": row["id"],
        "user_id": row["user_id"] if "user_id" in row.keys() else None,
        "code": row["code"] if "code" in row.keys() else "",
        "make": row["make"] if "make" in row.keys() else "",
        "model": row["model"] if "model" in row.keys() else "",
        "engine": row["engine"] if "engine" in row.keys() and row["engine"] else "",
        "symptoms": row["symptoms"] if "symptoms" in row.keys() and row["symptoms"] else "",
        "status": status,
        "created_at": row["created_at"] if "created_at" in row.keys() else "",
        "title": row["title"] if "title" in row.keys() and row["title"] else result.get("title", ""),
        "description": row["description"] if "description" in row.keys() and row["description"] else result.get("description", ""),
        "final_cause": row["final_cause"] if "final_cause" in row.keys() and row["final_cause"] else "",
        "final_fix": row["final_fix"] if "final_fix" in row.keys() and row["final_fix"] else "",
        "notes": notes,
        "resolution_image_path": row["resolution_image_path"] if "resolution_image_path" in row.keys() and row["resolution_image_path"] else "",
        "initial_image_path": row["initial_image_path"] if "initial_image_path" in row.keys() and row["initial_image_path"] else "",
        "requires_resolution_image": requires_resolution_image,
        "resolved": resolved,
        "closed_at": row["closed_at"] if "closed_at" in row.keys() and row["closed_at"] else "",
        "is_closed": 1 if resolved == 1 else 0,
    }


def register_history_routes(app):
    @app.route("/history")
    @login_required
    def history():
        current_user = get_current_user()
        items = get_history_for_user(current_user["id"])

        enriched_items = []
        for item in items:
            feedback = get_user_feedback_for_diagnosis(current_user["id"], item["id"])
            item["user_feedback"] = None if not feedback else feedback["helpful"]
            enriched_items.append(item)

        return render_template(
            "history.html",
            current_user=current_user,
            items=enriched_items,
        )

    @app.route("/history/close-ticket/<int:diagnosis_id>", methods=["POST"])
    @login_required
    def close_ticket_by_user_route(diagnosis_id):
        current_user = get_current_user()

        final_cause = request.form.get("final_cause", "").strip()
        final_fix = request.form.get("final_fix", "").strip()
        notes = request.form.get("notes", "").strip()
        resolution_image = request.files.get("resolution_image")

        if not final_cause or not final_fix or not resolution_image or not resolution_image.filename:
            return redirect(url_for("history"))

        row = get_diagnosis_by_id(diagnosis_id)
        if not row:
            return redirect(url_for("history"))

        if row["user_id"] != current_user["id"]:
            return redirect(url_for("history"))

        resolution_image_path = save_resolution_image(resolution_image, diagnosis_id)
        if not resolution_image_path:
            return redirect(url_for("history"))

        close_diagnosis_by_user(
            diagnosis_id=diagnosis_id,
            user_id=current_user["id"],
            final_cause=final_cause,
            final_fix=final_fix,
            notes=notes,
            resolution_image_path=resolution_image_path,
        )

        return redirect(url_for("history"))

    # -----------------------------
    # API ROUTET ANDROIDILLE
    # -----------------------------

    @app.route("/api/history", methods=["GET"])
    def api_history():
        current_user = get_current_user()

        if not current_user:
            return jsonify({
                "success": False,
                "message": "Kirjautuminen vaaditaan."
            }), 401

        items = get_history_for_user(current_user["id"])

        enriched_items = []
        for item in items:
            feedback = get_user_feedback_for_diagnosis(current_user["id"], item["id"])
            item["user_feedback"] = None if not feedback else feedback["helpful"]
            enriched_items.append(item)

        return jsonify({
            "success": True,
            "items": enriched_items
        }), 200

    @app.route("/api/history/<int:diagnosis_id>", methods=["GET"])
    def api_history_item(diagnosis_id):
        current_user = get_current_user()

        if not current_user:
            return jsonify({
                "success": False,
                "message": "Kirjautuminen vaaditaan."
            }), 401

        row = get_diagnosis_by_id(diagnosis_id)

        if not row:
            return jsonify({
                "success": False,
                "message": "Tietoa ei löytynyt."
            }), 404

        if row["user_id"] != current_user["id"]:
            return jsonify({
                "success": False,
                "message": "Ei oikeuksia tähän tietoon."
            }), 403

        item = serialize_history_item(row)
        feedback = get_user_feedback_for_diagnosis(current_user["id"], diagnosis_id)
        item["user_feedback"] = None if not feedback else feedback["helpful"]

        return jsonify({
            "success": True,
            "item": item
        }), 200

    @app.route("/api/history/close-ticket/<int:diagnosis_id>", methods=["POST"])
    def api_close_ticket_by_user(diagnosis_id):
        current_user = get_current_user()

        if not current_user:
            return jsonify({
                "success": False,
                "message": "Kirjautuminen vaaditaan."
            }), 401

        final_cause = request.form.get("final_cause", "").strip()
        final_fix = request.form.get("final_fix", "").strip()
        notes = request.form.get("notes", "").strip()
        resolution_image = request.files.get("resolution_image")

        if not final_cause or not final_fix:
            return jsonify({
                "success": False,
                "message": "Kentät final_cause ja final_fix ovat pakollisia."
            }), 400

        if not resolution_image or not resolution_image.filename:
            return jsonify({
                "success": False,
                "message": "Ratkaisukuva on pakollinen."
            }), 400

        row = get_diagnosis_by_id(diagnosis_id)

        if not row:
            return jsonify({
                "success": False,
                "message": "Tikettiä ei löytynyt."
            }), 404

        if row["user_id"] != current_user["id"]:
            return jsonify({
                "success": False,
                "message": "Ei oikeuksia tähän tikettiin."
            }), 403

        resolution_image_path = save_resolution_image(resolution_image, diagnosis_id)

        if not resolution_image_path:
            return jsonify({
                "success": False,
                "message": "Sallittuja kuvatyyppejä ovat jpg, jpeg, png ja webp."
            }), 400

        close_diagnosis_by_user(
            diagnosis_id=diagnosis_id,
            user_id=current_user["id"],
            final_cause=final_cause,
            final_fix=final_fix,
            notes=notes,
            resolution_image_path=resolution_image_path,
        )

        return jsonify({
            "success": True,
            "message": "Tiketti suljettu onnistuneesti.",
            "resolution_image_path": resolution_image_path
        }), 200