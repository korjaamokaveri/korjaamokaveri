from flask import Blueprint, render_template, request, redirect, url_for

from decorators import admin_required, get_current_user
from services.repair_guide_formatter import format_repair_guide
from services.repair_guide_service import (
    get_all_requests,
    get_request_by_id,
    create_repair_guide_from_request,
    get_all_repair_guides,
    get_repair_guide_by_id,
    update_repair_guide,
)

admin_repair_guides_bp = Blueprint("admin_repair_guides", __name__)


@admin_repair_guides_bp.route("/admin/repair-guide-requests")
@admin_required
def admin_repair_guide_requests():
    return render_template(
        "admin_repair_guide_requests.html",
        items=get_all_requests(),
        success=request.args.get("success"),
    )


@admin_repair_guides_bp.route("/admin/repair-guide-requests/<int:request_id>/create", methods=["GET", "POST"])
@admin_required
def admin_create_repair_guide(request_id):
    item = get_request_by_id(request_id)

    if not item:
        return "Korjausohjepyyntöä ei löytynyt", 404

    if request.method == "POST":
        current_user = get_current_user()

        title = request.form.get("title", "").strip()
        steps = request.form.get("steps", "").strip()
        tools = request.form.get("tools", "").strip()
        notes = request.form.get("notes", "").strip()
        vin_prefix = request.form.get("vin_prefix", "").strip()
        make = request.form.get("make", "").strip()
        part_name = request.form.get("part_name", "").strip()

        if not make or not part_name or not steps:
            return render_template(
                "admin_repair_guide_form.html",
                item=item,
                error="Täytä vähintään merkki, osa ja työvaiheet.",
                success=None,
            )

        create_repair_guide_from_request(
            request_id=request_id,
            created_by_user_id=current_user["id"],
            make=make,
            part_name=part_name,
            vin_prefix=vin_prefix,
            title=title,
            steps=steps,
            tools=tools,
            notes=notes,
        )

        return redirect(url_for(
            "admin_repair_guides.admin_repair_guide_requests",
            success="Korjausohje luotu ja pyyntö merkitty valmiiksi."
        ))

    return render_template(
        "admin_repair_guide_form.html",
        item=item,
        error=None,
        success=None,
    )


@admin_repair_guides_bp.route("/admin/repair-guides")
@admin_required
def admin_repair_guides():
    items = [format_repair_guide(row) for row in get_all_repair_guides()]

    grouped_items = {}

    for item in items:
        make = (item.get("make") or "Yleinen").strip()
        if not make:
            make = "Yleinen"

        if make not in grouped_items:
            grouped_items[make] = []

        grouped_items[make].append(item)

    return render_template(
        "admin_repair_guides.html",
        grouped_items=grouped_items,
        success=request.args.get("success"),
    )


@admin_repair_guides_bp.route("/admin/repair-guides/<int:guide_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_repair_guide(guide_id):
    item = get_repair_guide_by_id(guide_id)

    if not item:
        return "Korjausohjetta ei löytynyt", 404

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        make = request.form.get("make", "").strip()
        part_name = request.form.get("part_name", "").strip()
        vin_prefix = request.form.get("vin_prefix", "").strip()
        steps = request.form.get("steps", "").strip()
        tools = request.form.get("tools", "").strip()
        notes = request.form.get("notes", "").strip()

        if not make or not part_name or not steps:
            return render_template(
                "admin_repair_guide_form.html",
                item=item,
                guide_mode=True,
                error="Täytä vähintään merkki, osa ja työvaiheet.",
                success=None,
            )

        update_repair_guide(
            guide_id=guide_id,
            make=make,
            part_name=part_name,
            vin_prefix=vin_prefix,
            title=title,
            steps=steps,
            tools=tools,
            notes=notes,
        )

        return redirect(url_for(
            "admin_repair_guides.admin_repair_guides",
            success="Korjausohje päivitetty."
        ))

    return render_template(
        "admin_repair_guide_form.html",
        item=item,
        guide_mode=True,
        error=None,
        success=None,
    )