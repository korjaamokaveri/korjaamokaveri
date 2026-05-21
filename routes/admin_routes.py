import os
import time
import sqlite3
from collections import OrderedDict

from flask import Blueprint, render_template, request, redirect, url_for, current_app
from werkzeug.utils import secure_filename

from decorators import admin_required, get_current_user
from utils.import_pdf_dtc import import_pdf
from services.fault_category_service import suggest_category_for_fault

from services.fault_code_service import (
    get_all_fault_codes,
    create_fault_code_with_details,
    delete_fault_code,
    get_fault_code_by_id,
    update_fault_code_with_details,
    find_fault_code,
)

from services.ticket_service import (
    get_open_diagnoses,
    get_unknown_code_tickets,
    get_all_diagnoses,
    get_diagnosis_by_id,
    get_diagnosis_admin_detail,
    close_diagnosis_as_admin,
    update_diagnosis_result,
    create_fault_code_from_ticket,
)

from services.user_service import (
    get_all_users_with_stats,
    get_user_by_id,
    set_user_admin_by_id,
    delete_user_by_id,
    count_admin_users,
    set_user_account_type,
    set_user_subscription,
    admin_update_user,
)

from services.suggestion_service import (
    list_suggested_updates,
    approve_suggested_update,
    reject_suggested_update,
    create_ai_enrichment_suggestions,
)

from services.accounting_service import (
    get_all_accounting_entries,
    get_accounting_summary,
)


try:
    import psycopg2
except ImportError:
    psycopg2 = None


admin_bp = Blueprint("admin", __name__)

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def is_integrity_error(error):
    if isinstance(error, sqlite3.IntegrityError):
        return True

    if psycopg2 and isinstance(error, psycopg2.Error):
        return getattr(error, "pgcode", None) == "23505"

    return False


def allowed_image_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_resolution_image(file_storage, diagnosis_id: int):
    if not file_storage or not file_storage.filename:
        return None

    if not allowed_image_file(file_storage.filename):
        return None

    filename = secure_filename(file_storage.filename)
    filename = f"ticket_{diagnosis_id}_{int(time.time())}_{filename}"

    upload_folder = os.path.join(current_app.static_folder, "uploads", "tickets")
    os.makedirs(upload_folder, exist_ok=True)

    save_path = os.path.join(upload_folder, filename)
    file_storage.save(save_path)

    return f"uploads/tickets/{filename}"


def group_by_system(codes):
    grouped = OrderedDict({
        "P": [],
        "B": [],
        "C": [],
        "U": [],
        "Other": [],
    })

    for item in codes:
        code = (item["code"] or "").upper()

        if code.startswith("P"):
            grouped["P"].append(item)
        elif code.startswith("B"):
            grouped["B"].append(item)
        elif code.startswith("C"):
            grouped["C"].append(item)
        elif code.startswith("U"):
            grouped["U"].append(item)
        else:
            grouped["Other"].append(item)

    return grouped


def group_fault_codes_by_make(fault_codes):
    grouped = OrderedDict()

    for row in fault_codes:
        try:
            make = (row["make"] or "").strip()
        except Exception:
            make = ""

        if not make:
            make = "Yleinen"

        if make not in grouped:
            grouped[make] = []

        grouped[make].append(row)

    for make in grouped:
        grouped[make] = group_by_system(grouped[make])

    return grouped
    
@admin_bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_user(user_id):

    user = get_user_by_id(user_id)

    if not user:
        return "Käyttäjää ei löytynyt", 404

    success = None

    if request.method == "POST":

        admin_update_user(
            user_id=user_id,
            full_name=request.form.get("full_name", ""),
            phone=request.form.get("phone", ""),
            address_line1=request.form.get("address_line1", ""),
            postal_code=request.form.get("postal_code", ""),
            city=request.form.get("city", ""),
            country=request.form.get("country", ""),
            customer_type=request.form.get("customer_type", "private"),
            company_name=request.form.get("company_name", ""),
            vat_number=request.form.get("vat_number", ""),
            account_type=request.form.get("account_type", "basic"),
            is_admin=1 if request.form.get("is_admin") == "1" else 0,
        )

        success = "Käyttäjän tiedot päivitetty."

        user = get_user_by_id(user_id)

    return render_template(
        "admin_edit_user.html",
        user=user,
        success=success,
    )

@admin_bp.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    error = None
    success = request.args.get("success")

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        make = request.form.get("make", "").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        problem_symptoms = request.form.get("problem_symptoms", "").strip()
        mil_status = request.form.get("mil_status", "").strip()
        fail_safe_function = request.form.get("fail_safe_function", "").strip()
        priority = request.form.get("priority", "").strip()
        sae_code = request.form.get("sae_code", "").strip()
        causes = request.form.get("causes", "").strip()
        steps = request.form.get("steps", "").strip()
        ticket_id = request.form.get("ticket_id", "").strip()

        if not code or not title or not description:
            error = "Täytä vähintään DTC, otsikko ja kuvaus."
        else:
            try:
                create_fault_code_with_details(
                    code=code,
                    make=make,
                    title=title,
                    description=description,
                    causes_text=causes,
                    steps_text=steps,
                    problem_symptoms=problem_symptoms,
                    mil_status=mil_status,
                    fail_safe_function=fail_safe_function,
                    priority=priority,
                    sae_code=sae_code,
                )

                row = find_fault_code(code)
                if row:
                    suggest_category_for_fault(
                        fault_code_id=row["id"],
                        code=row["code"],
                        title=row["title"],
                        description=row["description"],
                )
                if row:
                    create_ai_enrichment_suggestions(row["id"])

                if ticket_id and row:
                    updated_result = {
                        "success": True,
                        "unknown_code": False,
                        "fault_code": row["code"],
                        "title": row["title"],
                        "description": row["description"],
                        "problem_symptoms": row["problem_symptoms"] or "",
                        "mil_status": row["mil_status"] or "",
                        "fail_safe_function": row["fail_safe_function"] or "",
                        "priority": row["priority"] or "",
                        "sae_code": row["sae_code"] or "",
                        "vehicle": {
                            "make": "",
                            "model": "",
                            "engine": "",
                        },
                        "matched_symptoms": [],
                        "symptom_notes": [],
                        "vehicle_notes": [],
                        "possible_causes": [],
                        "test_steps": [],
                        "top_solution": None,
                        "top_solution_with_image": None,
                    }

                    update_diagnosis_result(int(ticket_id), updated_result)

                return redirect(url_for("admin.admin", success=f"DTC {code.upper()} tallennettu."))

            except Exception as e:
                if is_integrity_error(e):
                    error = "Tämä DTC on jo olemassa."
                else:
                    raise

    fault_codes = get_all_fault_codes()
    grouped_fault_codes = group_fault_codes_by_make(fault_codes)

    return render_template(
        "admin.html",
        error=error,
        success=success,
        fault_codes=fault_codes,
        grouped_fault_codes=grouped_fault_codes,
        prefill=None,
    )


@admin_bp.route("/admin/edit/<int:fault_code_id>", methods=["GET", "POST"])
@admin_required
def edit_fault_code_route(fault_code_id):
    item = get_fault_code_by_id(fault_code_id)

    if not item:
        return "DTC:tä ei löytynyt", 404

    error = None

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        make = request.form.get("make", "").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        problem_symptoms = request.form.get("problem_symptoms", "").strip()
        mil_status = request.form.get("mil_status", "").strip()
        fail_safe_function = request.form.get("fail_safe_function", "").strip()
        priority = request.form.get("priority", "").strip()
        sae_code = request.form.get("sae_code", "").strip()
        causes = request.form.get("causes", "").strip()
        steps = request.form.get("steps", "").strip()

        if not code or not title or not description:
            error = "Täytä vähintään DTC, otsikko ja kuvaus."
        else:
            try:
                update_fault_code_with_details(
                    fault_code_id=fault_code_id,
                    code=code,
                    make=make,
                    title=title,
                    description=description,
                    causes_text=causes,
                    steps_text=steps,
                    problem_symptoms=problem_symptoms,
                    mil_status=mil_status,
                    fail_safe_function=fail_safe_function,
                    priority=priority,
                    sae_code=sae_code,
                )

                create_ai_enrichment_suggestions(fault_code_id)

                return redirect(
                    url_for("admin.admin", success=f"DTC {code.upper()} päivitetty.")
                    + f"#fault-{fault_code_id}"
                )

            except Exception as e:
                if is_integrity_error(e):
                    error = "Tämä DTC on jo olemassa."
                else:
                    raise

        item = get_fault_code_by_id(fault_code_id)

    return render_template(
        "admin_edit.html",
        item=item,
        error=error,
        success=None,
    )


@admin_bp.route("/admin/delete/<int:fault_code_id>", methods=["POST"])
@admin_required
def delete_fault_code_route(fault_code_id):
    delete_fault_code(fault_code_id)
    return redirect(url_for("admin.admin", success="DTC poistettu."))


@admin_bp.route("/admin/import-dtc-pdf", methods=["POST"])
@admin_required
def admin_import_dtc_pdf():
    pdf_file = request.files.get("pdf_file")
    make = request.form.get("make", "Yleinen").strip() or "Yleinen"

    if not pdf_file or not pdf_file.filename:
        return redirect(url_for("admin.admin", success="PDF-tiedosto puuttuu."))

    if not pdf_file.filename.lower().endswith(".pdf"):
        return redirect(url_for("admin.admin", success="Vain PDF-tiedostot sallitaan."))

    filename = secure_filename(pdf_file.filename)
    upload_folder = os.path.join(current_app.instance_path, "imports")
    os.makedirs(upload_folder, exist_ok=True)

    save_path = os.path.join(upload_folder, filename)
    pdf_file.save(save_path)

    import_pdf(save_path, make)

    return redirect(url_for(
        "admin.admin",
        success=f"PDF-import valmis merkille {make}."
    ))


@admin_bp.route("/admin/tickets")
@admin_required
def admin_tickets():
    return render_template(
        "admin_tickets.html",
        tickets=get_open_diagnoses(),
        success=request.args.get("success"),
    )


@admin_bp.route("/admin/unknown-tickets")
@admin_required
def admin_unknown_tickets():
    return render_template(
        "admin_unknown_tickets.html",
        tickets=get_unknown_code_tickets(),
        success=request.args.get("success"),
    )


@admin_bp.route("/admin/all-tickets")
@admin_required
def admin_all_tickets():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()

    return render_template(
        "admin_all_tickets.html",
        tickets=get_all_diagnoses(search=q, status=status),
        q=q,
        status=status,
    )


@admin_bp.route("/admin/ticket/<int:diagnosis_id>")
@admin_required
def admin_ticket_detail(diagnosis_id):
    item = get_diagnosis_admin_detail(diagnosis_id)

    if not item:
        return "Tikettiä ei löytynyt", 404

    return render_template("admin_ticket_detail.html", item=item)


@admin_bp.route("/admin/users")
@admin_required
def admin_users():
    return render_template(
        "admin_users.html",
        users=get_all_users_with_stats(),
        current_user=get_current_user(),
    )


@admin_bp.route("/admin/accounting")
@admin_required
def admin_accounting():
    items = get_all_accounting_entries()
    summary, grouped = get_accounting_summary()

    return render_template(
        "admin_accounting.html",
        items=items,
        summary=summary,
        grouped=grouped,
    )


@admin_bp.route("/admin/users/<int:user_id>/make-admin", methods=["POST"])
@admin_required
def admin_make_user_admin(user_id):
    current_user = get_current_user()
    target_user = get_user_by_id(user_id)

    if not target_user:
        return redirect(url_for("admin.admin_users"))

    if current_user["id"] == user_id:
        return redirect(url_for("admin.admin_users"))

    set_user_admin_by_id(user_id, True)
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/users/<int:user_id>/make-basic", methods=["POST"])
@admin_required
def admin_make_user_basic(user_id):
    current_user = get_current_user()
    target_user = get_user_by_id(user_id)

    if not target_user:
        return redirect(url_for("admin.admin_users"))

    if current_user["id"] == user_id:
        return redirect(url_for("admin.admin_users"))

    if target_user["is_admin"] == 1 and count_admin_users() <= 1:
        return redirect(url_for("admin.admin_users"))

    set_user_admin_by_id(user_id, False)
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/users/<int:user_id>/set-account-type", methods=["POST"])
@admin_required
def admin_set_account_type(user_id):
    target_user = get_user_by_id(user_id)

    if not target_user:
        return redirect(url_for("admin.admin_users"))

    account_type = request.form.get("account_type", "basic").strip().lower()
    subscription_status = request.form.get("subscription_status", "inactive").strip().lower()

    if account_type not in {"basic", "test"}:
        account_type = "basic"

    if subscription_status not in {"inactive", "active", "cancelled", "past_due"}:
        subscription_status = "inactive"

    set_user_account_type(user_id, account_type)

    if account_type == "test":
        set_user_subscription(
            user_id=user_id,
            subscription_status="inactive",
            subscription_started_at=None,
            subscription_expires_at=None,
        )
    else:
        set_user_subscription(
            user_id=user_id,
            subscription_status=subscription_status,
            subscription_started_at=None,
            subscription_expires_at=None,
        )

    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    current_user = get_current_user()
    target_user = get_user_by_id(user_id)

    if not target_user:
        return redirect(url_for("admin.admin_users"))

    if current_user["id"] == user_id:
        return redirect(url_for("admin.admin_users"))

    if target_user["is_admin"] == 1 and count_admin_users() <= 1:
        return redirect(url_for("admin.admin_users"))

    delete_user_by_id(user_id)
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/suggestions")
@admin_required
def admin_suggestions():
    success = request.args.get("success")
    status = request.args.get("status", "pending").strip()
    items = list_suggested_updates(status=status)

    return render_template(
        "admin_suggestions.html",
        items=items,
        status=status,
        success=success,
    )


@admin_bp.route("/admin/suggestions/<int:suggestion_id>/approve", methods=["POST"])
@admin_required
def approve_suggestion_route(suggestion_id):
    current_user = get_current_user()
    admin_note = request.form.get("admin_note", "").strip()

    ok, message = approve_suggested_update(
        suggestion_id=suggestion_id,
        reviewed_by_user_id=current_user["id"],
        admin_note=admin_note,
    )

    return redirect(url_for("admin.admin_suggestions", success=message))


@admin_bp.route("/admin/suggestions/<int:suggestion_id>/reject", methods=["POST"])
@admin_required
def reject_suggestion_route(suggestion_id):
    current_user = get_current_user()
    admin_note = request.form.get("admin_note", "").strip()

    ok, message = reject_suggested_update(
        suggestion_id=suggestion_id,
        reviewed_by_user_id=current_user["id"],
        admin_note=admin_note,
    )

    return redirect(url_for("admin.admin_suggestions", success=message))


@admin_bp.route("/admin/create-from-ticket/<int:diagnosis_id>", methods=["GET"])
@admin_required
def create_from_ticket(diagnosis_id):
    row = get_diagnosis_by_id(diagnosis_id)

    if not row:
        return "Tikettiä ei löytynyt", 404

    fault_codes = get_all_fault_codes()
    grouped_fault_codes = group_fault_codes_by_make(fault_codes)

    return render_template(
        "admin.html",
        error=None,
        success=None,
        fault_codes=fault_codes,
        grouped_fault_codes=grouped_fault_codes,
        prefill={
            "code": row["code"],
            "make": row["make"] or "Yleinen",
            "title": "",
            "description": f"Automaattisesti luotu tiketin perusteella ({row['make']} {row['model']})",
            "problem_symptoms": row["symptoms"] or "",
            "mil_status": "",
            "fail_safe_function": "",
            "priority": "",
            "sae_code": "",
            "causes": "",
            "steps": "",
            "ticket_id": row["id"],
        },
    )


@admin_bp.route("/admin/answer/<int:diagnosis_id>", methods=["POST"])
@admin_required
def admin_answer_ticket(diagnosis_id):
    final_cause = request.form.get("final_cause", "").strip()
    final_fix = request.form.get("final_fix", "").strip()
    notes = request.form.get("notes", "").strip()

    create_fault_code = request.form.get("create_fault_code", "").strip() == "yes"
    new_title = request.form.get("new_title", "").strip()
    new_description = request.form.get("new_description", "").strip()

    if not final_cause or not final_fix:
        return redirect(url_for("admin.admin_unknown_tickets"))

    row = get_diagnosis_by_id(diagnosis_id)
    if not row:
        return "Tikettiä ei löytynyt", 404

    resolution_image = request.files.get("resolution_image")
    resolution_image_path = save_resolution_image(resolution_image, diagnosis_id)

    if resolution_image and resolution_image.filename and not resolution_image_path:
        return redirect(
            url_for(
                "admin.admin_unknown_tickets",
                success="Virhe: sallittuja kuvatyyppejä ovat jpg, jpeg, png ja webp."
            )
        )

    if create_fault_code:
        if not new_title:
            new_title = f"Adminin luoma DTC {row['code']}"
        if not new_description:
            new_description = f"Luotu ratkaistun tiketin perusteella ({row['make']} {row['model']})"

        try:
            create_fault_code_from_ticket(
                code=row["code"],
                make=row["make"],
                title=new_title,
                description=new_description,
                final_cause=final_cause,
            )
        except Exception as e:
            if not is_integrity_error(e):
                raise

        fault = find_fault_code(row["code"])
        if fault:
            create_ai_enrichment_suggestions(fault["id"])

            updated_result = {
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
                    "make": row["make"],
                    "model": row["model"],
                    "engine": row["engine"] or "",
                },
                "matched_symptoms": [],
                "symptom_notes": [],
                "vehicle_notes": [],
                "possible_causes": [],
                "test_steps": [],
                "top_solution": None,
                "top_solution_with_image": None,
            }

            update_diagnosis_result(diagnosis_id, updated_result)

    close_diagnosis_as_admin(
        diagnosis_id=diagnosis_id,
        final_cause=final_cause,
        final_fix=final_fix,
        notes=notes,
        resolution_image_path=resolution_image_path,
    )

    return redirect(url_for("admin.admin_unknown_tickets", success="Tiketti käsitelty"))
