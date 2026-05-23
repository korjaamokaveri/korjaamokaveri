import os
import time

import stripe
from flask import render_template, request, jsonify, current_app, redirect, url_for, session
from werkzeug.utils import secure_filename
from services.email_service import send_email
from utils.config import Config
from utils.auth import get_current_user
from decorators import base_system_required
from services.user_service import (
    can_user_view_repair_guides,
    update_user_profile,
    get_user_by_id,
)
from services.diagnostics_service import diagnose
from services.vin_service import detect_vehicle_identifier
from services.ticket_service import (
    save_diagnosis,
    count_open_tickets_missing_resolution_image,
    save_solution_feedback,
    get_popular_repairs,
    get_diagnosis_by_id,
)
from services.payment_service import ensure_one_time_purchase
from services.repair_guide_service import (
    create_request,
    get_user_requests,
)
from services.repair_guide_service import (
    create_request,
    get_user_requests,
    get_repair_guide_by_id_for_user,
)
from services.user_service import (
    can_user_view_repair_guides,
    update_user_profile,
    get_user_by_id,
    admin_update_user,
)
stripe.api_key = Config.STRIPE_SECRET_KEY

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def allowed_image_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def save_initial_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None

    if not allowed_image_file(file_storage.filename):
        return None

    filename = secure_filename(file_storage.filename)
    filename = f"initial_{int(time.time())}_{filename}"

    upload_folder = os.path.join(current_app.static_folder, "uploads", "tickets")
    os.makedirs(upload_folder, exist_ok=True)

    save_path = os.path.join(upload_folder, filename)
    file_storage.save(save_path)

    return f"uploads/tickets/{filename}"


def parse_vehicle_identifier(raw_value: str, make: str):
    vehicle_id_info = detect_vehicle_identifier(raw_value)
    vehicle_identifier = vehicle_id_info["value"]

    if not make and vehicle_id_info["detected_make"]:
        make = vehicle_id_info["detected_make"]

    return vehicle_identifier, make, vehicle_id_info

def register_main_routes(app):
    @app.route("/", methods=["GET"])
    def landing():
        current_user = get_current_user()
        if current_user:
            return redirect(url_for("app_home"))
        return render_template("landing.html")
    @app.route("/set-language/<lang>")
    def set_language(lang):
        if lang in ["fi", "en"]:
            session["lang"] = lang

        return redirect(request.referrer or url_for("landing"))
        
    @app.route("/app", methods=["GET"])
    @base_system_required
    def app_home():
        current_user = get_current_user()
        return render_template(
            "home.html",
            result=None,
            error=None,
            success_message=None,
            form_data=None,
            diagnosis_id=None,
            user_feedback=None,
            repair_guide=None,
            can_view_repair_guide=can_user_view_repair_guides(current_user),
        )

    @app.route("/subscription-required", methods=["GET"])
    def subscription_required():
        current_user = get_current_user()

        if not current_user:
            return redirect(url_for("login"))

        if current_user["is_admin"] == 1:
            return redirect(url_for("app_home"))

        return render_template(
            "subscription_required.html",
            current_user=current_user,
            success=request.args.get("success"),
        )
   
    @app.route("/create-checkout-session", methods=["POST"])
    def create_checkout_session():
        current_user = get_current_user()

        if not current_user:
            return redirect(url_for("login"))

        if not Config.STRIPE_SECRET_KEY or not Config.STRIPE_PRICE_BASIC:
            return redirect(url_for(
                "subscription_required",
                success="Stripe-asetukset puuttuvat."
            ))

        ensure_one_time_purchase(
            user_id=current_user["id"],
            product_type="basic_subscription",
            product_key="basic",
        )

        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price": Config.STRIPE_PRICE_BASIC,
                    "quantity": 1,
                }
            ],
            customer_email=current_user["email"],
            client_reference_id=str(current_user["id"]),
            metadata={
                "user_id": str(current_user["id"]),
                "product_type": "basic_subscription",
                "product_key": "basic",
            },
            success_url=f"{Config.BASE_URL}/subscription-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{Config.BASE_URL}/subscription-cancel",
        )

        return redirect(checkout_session.url, code=303)
        
    @app.route("/account", methods=["GET", "POST"])
    def account():

        current_user = get_current_user()

        if not current_user:
            return redirect(url_for("login"))

        error = None
        success = None

        if request.method == "POST":

            update_user_profile(
                user_id=current_user["id"],
                full_name=request.form.get("full_name", ""),
                phone=request.form.get("phone", ""),
                address_line1=request.form.get("address_line1", ""),
                postal_code=request.form.get("postal_code", ""),
                city=request.form.get("city", ""),
                country=request.form.get("country", ""),
                customer_type=request.form.get("customer_type", "private"),
                company_name=request.form.get("company_name", ""),
                vat_number=request.form.get("vat_number", ""),
            )

            success = "Tiedot päivitetty onnistuneesti."

            current_user = get_user_by_id(current_user["id"])
            
            print("ACCOUNT DEBUG:", dict(current_user) if current_user else None, flush=True)
            
        return render_template(
            "account.html",
            current_user=current_user,
            success=success,
            error=error,
        )
        
    @app.route("/payment-coming-soon", methods=["POST"])
    def payment_coming_soon():
        return redirect(url_for("create_checkout_session"), code=307)

    @app.route("/subscription-success", methods=["GET"])
    def subscription_success():
        return render_template(
            "subscription_required.html",
            current_user=get_current_user(),
            success="Maksu vastaanotettu. Tilaus aktivoituu webhook-vahvistuksen jälkeen.",
        )

    @app.route("/subscription-cancel", methods=["GET"])
    def subscription_cancel():
        return render_template(
            "subscription_required.html",
            current_user=get_current_user(),
            success="Maksu peruttiin.",
        )

    @app.route("/order-repair-guide", methods=["GET", "POST"])
    @base_system_required
    def order_repair_guide():
        current_user = get_current_user()

        if request.method == "POST":
            make = request.form.get("make", "").strip()
            vehicle_input = request.form.get("vehicle_input", "").strip()
            part_name = request.form.get("part_name", "").strip()
            note = request.form.get("note", "").strip()

            if not make or not vehicle_input or not part_name:
                return render_template(
                    "order_repair_guide.html",
                    items=get_user_requests(current_user["id"]),
                    error="Täytä merkki, VIN/rekisterinumero ja vaihdettava osa.",
                    success=None,
                )

            create_request(
                user_id=current_user["id"],
                make=make,
                vehicle_input=vehicle_input,
                part_name=part_name,
                note=note,
            )

            return render_template(
                "order_repair_guide.html",
                items=get_user_requests(current_user["id"]),
                error=None,
                success="Korjausohjepyyntö lähetetty adminille.",
            )

        return render_template(
            "order_repair_guide.html",
            items=get_user_requests(current_user["id"]),
            error=None,
            success=None,
        )

    @app.route("/terms", methods=["GET"])
    def terms():
        return render_template("terms.html")

    @app.route("/privacy", methods=["GET"])
    def privacy():
        return render_template("privacy.html")

    @app.route("/contact", methods=["GET", "POST"])
    def contact():
        error = None
        success = None
        name = ""
        email = ""
        message = ""

        if request.method == "POST":

            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            message = request.form.get("message", "").strip()

            if not name or not email or not message:

                error = "Täytä kaikki kentät."

            else:

                ok = send_email(
                    to_email="asiakaspalvelu@korjaamokaveri.fi",
                    subject=f"Yhteydenotto: {name}",
                    body=f"""Uusi yhteydenotto Korjaamo Kaverista

    Nimi: {name}
    Sähköposti: {email}

    Viesti:
    {message}
    """
                )

                send_email(
                    to_email=email,
                    subject="Korjaamo Kaveri - viestisi vastaanotettu",
                    body=f"""Hei {name},

    Kiitos viestistäsi.

    Olemme vastaanottaneet yhteydenottosi ja vastaamme yleensä 24 tunnin sisällä.

    Terveisin,
    Korjaamo Kaveri
    """
                )
 
                if ok:

                    success = "Viestisi on lähetetty onnistuneesti."

                    name = ""
                    email = ""
                    message = ""

                else:

                    error = "Viestin lähetys epäonnistui."

        return render_template(
            "contact.html",
            error=error,
            success=success,
            name=name,
            email=email,
            message=message,
        )
        
    @app.route("/popular-repairs", methods=["GET"])
    def popular_repairs_page():
        return render_template("popular_repairs.html", items=get_popular_repairs())

    @app.route("/ui-feedback", methods=["POST"])
    @base_system_required
    def ui_feedback():
        current_user = get_current_user()

        fault_code = request.form.get("fault_code", "").strip()
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        vehicle = request.form.get("vehicle", "").strip()
        helpful_raw = request.form.get("helpful", "").strip().lower()
        diagnosis_id_raw = request.form.get("diagnosis_id", "").strip()

        if helpful_raw not in {"1", "0", "true", "false", "yes", "no"}:
            return redirect(request.referrer or url_for("app_home"))

        helpful = helpful_raw in {"1", "true", "yes"}
        diagnosis_id = int(diagnosis_id_raw) if diagnosis_id_raw.isdigit() else None

        if diagnosis_id is not None:
            row = get_diagnosis_by_id(diagnosis_id)
            if not row:
                return redirect(request.referrer or url_for("app_home"))
            if row["user_id"] != current_user["id"] and current_user["is_admin"] != 1:
                return redirect(request.referrer or url_for("app_home"))

        save_solution_feedback(
            user_id=current_user["id"],
            diagnosis_id=diagnosis_id,
            fault_code=fault_code,
            title=title,
            description=description,
            vehicle=vehicle,
            helpful=helpful,
        )

        return redirect(request.referrer or url_for("app_home"))
        
    @app.route("/repair-guide/<int:guide_id>")
    @base_system_required
    def repair_guide_detail(guide_id):
        current_user = get_current_user()

        guide = get_repair_guide_by_id_for_user(
            guide_id=guide_id,
            user_id=current_user["id"],
            is_admin=current_user["is_admin"] == 1,
        )

        if not guide:
            return "Ohjetta ei löytynyt", 404

        return render_template("repair_guide_detail.html", guide=guide)
    
    @app.route("/api/diagnose", methods=["POST"])
    def diagnose_api():
        data = request.get_json(silent=True) or {}

        code = data.get("code", "").strip()
        make = data.get("make", "").strip()
        vehicle_input = data.get("vin", "").strip() or data.get("vehicle_input", "").strip()
        symptoms = data.get("symptoms", "").strip()

        vehicle_identifier, make, vehicle_id_info = parse_vehicle_identifier(vehicle_input, make)

        if not code or not make or not vehicle_identifier or not symptoms:
            return jsonify({
                "success": False,
                "message": "Kentät code, make, vin/vehicle_input ja symptoms ovat pakollisia. Jos VIN tunnistetaan, merkki voidaan tunnistaa automaattisesti."
            }), 400

        result = diagnose(code, make, vehicle_identifier, symptoms, "")
        current_user = get_current_user()

        ticket_created = False
        history_saved = False
        diagnosis_id = None

        if current_user:
            if not result.get("success"):
                if current_user["is_admin"] == 0:
                    open_ticket_count = count_open_tickets_missing_resolution_image(current_user["id"])
                    if open_ticket_count >= 3:
                        return jsonify({
                            "success": False,
                            "ticket_created": False,
                            "history_saved": False,
                            "message": "Sinulla on liikaa avoimia tikettejä ilman ratkaisukuvaa. Sulje vanhat tiketit lisäämällä kuva ennen uuden tiketin tekemistä."
                        }), 400

                diagnosis_id = save_diagnosis(
                    user_id=current_user["id"],
                    code=code,
                    make=make,
                    model=vehicle_identifier,
                    engine="",
                    symptoms=symptoms,
                    result=result,
                    initial_image_path=None,
                )

                return jsonify({
                    "success": False,
                    "ticket_created": True,
                    "history_saved": True,
                    "diagnosis_id": diagnosis_id,
                    "repair_guide": None,
                    "message": (
                        "Vikakoodia ei löytynyt järjestelmästä. Tiketti on vastaanotettu "
                        "ja vastaamme sinulle 24 tunnin kuluessa. Löydät vastauksen tikettihistoriasta."
                    )
                }), 200

            diagnosis_id = save_diagnosis(
                user_id=current_user["id"],
                code=code,
                make=make,
                model=vehicle_identifier,
                engine="",
                symptoms=symptoms,
                result=result,
                initial_image_path=None,
            )
            history_saved = True

        response_data = dict(result)
        response_data["ticket_created"] = ticket_created
        response_data["history_saved"] = history_saved
        response_data["diagnosis_id"] = diagnosis_id
        response_data["repair_guide"] = None
        response_data["vehicle_identifier_type"] = vehicle_id_info["type"]

        return jsonify(response_data), 200
   
    @app.route("/api/order-repair-guide", methods=["POST"])
    @base_system_required
    def api_order_repair_guide():
        current_user = get_current_user()

        if not current_user:
            return jsonify({
                "success": False,
                "message": "Kirjautuminen vaaditaan."
            }), 401

        data = request.get_json(silent=True) or {}

        make = data.get("make", "").strip()
        vehicle_input = data.get("vehicle_input", "").strip()
        part_name = data.get("part_name", "").strip()
        note = data.get("note", "").strip()

        if not make or not vehicle_input or not part_name:
            return jsonify({
                "success": False,
                "message": "Kentät make, vehicle_input ja part_name ovat pakollisia."
            }), 400

        create_request(
            user_id=current_user["id"],
            make=make,
            vehicle_input=vehicle_input,
            part_name=part_name,
            note=note,
        )

        return jsonify({
            "success": True,
            "message": "Korjausohjepyyntö lähetetty adminille."
        }), 200

    @app.route("/api/feedback", methods=["POST"])
    def api_feedback():
        current_user = get_current_user()

        if not current_user:
            return jsonify({
                "success": False,
                "message": "Kirjautuminen vaaditaan."
            }), 401

        data = request.get_json(silent=True) or {}

        fault_code = data.get("fault_code", "").strip()
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        vehicle = data.get("vehicle", "").strip()
        helpful = data.get("helpful", None)
        diagnosis_id = data.get("diagnosis_id", None)

        if not fault_code:
            return jsonify({"success": False, "message": "fault_code puuttuu."}), 400

        if helpful is None:
            return jsonify({"success": False, "message": "helpful puuttuu."}), 400

        parsed_diagnosis_id = None
        if isinstance(diagnosis_id, int):
            parsed_diagnosis_id = diagnosis_id
        elif isinstance(diagnosis_id, str) and diagnosis_id.isdigit():
            parsed_diagnosis_id = int(diagnosis_id)

        if parsed_diagnosis_id is not None:
            row = get_diagnosis_by_id(parsed_diagnosis_id)

            if not row:
                return jsonify({"success": False, "message": "Tikettiä ei löytynyt."}), 404

            if row["user_id"] != current_user["id"] and current_user["is_admin"] != 1:
                return jsonify({"success": False, "message": "Ei oikeutta tähän tikettiin."}), 403

        save_solution_feedback(
            user_id=current_user["id"],
            diagnosis_id=parsed_diagnosis_id,
            fault_code=fault_code,
            title=title,
            description=description,
            vehicle=vehicle,
            helpful=bool(helpful),
        )

        return jsonify({
            "success": True,
            "message": "Palaute tallennettu."
        }), 200

    @app.route("/api/popular-repairs", methods=["GET"])
    def api_popular_repairs():
        return jsonify({
            "success": True,
            "items": get_popular_repairs()
        }), 200

    @app.route("/diagnose", methods=["POST"])
    def diagnose_route():
        data = request.get_json(silent=True) or {}

        code = data.get("code", "").strip()
        make = data.get("make", "").strip()
        vehicle_input = data.get("vin", "").strip() or data.get("vehicle_input", "").strip()
        symptoms = data.get("symptoms", "").strip()

        vehicle_identifier, make, vehicle_id_info = parse_vehicle_identifier(vehicle_input, make)

        if not code or not make or not vehicle_identifier or not symptoms:
            return jsonify({
                "success": False,
                "message": "Kentät code, make, vin/vehicle_input ja symptoms ovat pakollisia."
            }), 400

        result = diagnose(code, make, vehicle_identifier, symptoms, "")
        status_code = 200 if result.get("success") else 404
        return jsonify(result), status_code

    @app.route("/ui-diagnose", methods=["POST"])
    @base_system_required
    def ui_diagnose():
        code = request.form.get("code", "").strip()
        make = request.form.get("make", "").strip()
        vehicle_input = request.form.get("vin", "").strip()
        symptoms = request.form.get("symptoms", "").strip()
        accept_terms = request.form.get("accept_terms", "")

        vehicle_identifier, make, vehicle_id_info = parse_vehicle_identifier(vehicle_input, make)

        form_data = {
            "code": code,
            "make": make,
            "vin": vehicle_identifier,
            "symptoms": symptoms,
            "accept_terms": accept_terms == "yes",
        }

        image = request.files.get("image")
        image_path = None

        current_user = get_current_user()
        can_view_repair_guide = can_user_view_repair_guides(current_user)

        if image and image.filename:
            image_path = save_initial_image(image)
            if not image_path:
                return render_template(
                    "home.html",
                    result=None,
                    error="Vain JPG, JPEG, PNG ja WEBP kuvat sallittu.",
                    success_message=None,
                    form_data=form_data,
                    diagnosis_id=None,
                    user_feedback=None,
                    repair_guide=None,
                    can_view_repair_guide=can_view_repair_guide,
                )

        if not code or not make or not vehicle_identifier or not symptoms:
            return render_template(
                "home.html",
                result=None,
                error="Täytä DTC, VIN tai rekisterinumero, oireet ja merkki. Jos VIN tunnistetaan, merkki täyttyy automaattisesti.",
                success_message=None,
                form_data=form_data,
                diagnosis_id=None,
                user_feedback=None,
                repair_guide=None,
                can_view_repair_guide=can_view_repair_guide,
            )

        if accept_terms != "yes":
            return render_template(
                "home.html",
                result=None,
                error="Sinun täytyy hyväksyä käyttöehdot ennen diagnoosin tekemistä.",
                success_message=None,
                form_data=form_data,
                diagnosis_id=None,
                user_feedback=None,
                repair_guide=None,
                can_view_repair_guide=can_view_repair_guide,
            )

        result = diagnose(code, make, vehicle_identifier, symptoms, "")

        diagnosis_id = None
        success_message = None

        if not result.get("success"):
            if current_user:
                if current_user["is_admin"] == 0:
                    open_ticket_count = count_open_tickets_missing_resolution_image(current_user["id"])
                    if open_ticket_count >= 3:
                        return render_template(
                            "home.html",
                            result=None,
                            error="Sinulla on liikaa avoimia tikettejä ilman ratkaisukuvaa. Sulje vanhat tiketit lisäämällä kuva ennen uuden tiketin tekemistä.",
                            success_message=None,
                            form_data=form_data,
                            diagnosis_id=None,
                            user_feedback=None,
                            repair_guide=None,
                            can_view_repair_guide=can_view_repair_guide,
                        )

                diagnosis_id = save_diagnosis(
                    user_id=current_user["id"],
                    code=code,
                    make=make,
                    model=vehicle_identifier,
                    engine="",
                    symptoms=symptoms,
                    result=result,
                    initial_image_path=image_path,
                )
                success_message = (
                    "Vikakoodia ei löytynyt järjestelmästä. Tiketti on vastaanotettu "
                    "ja vastaamme sinulle 24 tunnin kuluessa. Löydät vastauksen tikettihistoriasta."
                )

            return render_template(
                "home.html",
                result=None,
                error=None,
                success_message=success_message or result.get("message", "Diagnoosi epäonnistui."),
                form_data=form_data,
                diagnosis_id=diagnosis_id,
                user_feedback=None,
                repair_guide=None,
                can_view_repair_guide=can_view_repair_guides(current_user),
            )

        if current_user:
            diagnosis_id = save_diagnosis(
                user_id=current_user["id"],
                code=code,
                make=make,
                model=vehicle_identifier,
                engine="",
                symptoms=symptoms,
                result=result,
                initial_image_path=image_path,
            )
            success_message = "Diagnoosi tallennettu historiaan."

        return render_template(
            "home.html",
            result=result,
            error=None,
            success_message=success_message,
            form_data=form_data,
            diagnosis_id=diagnosis_id,
            user_feedback=None,
            repair_guide=None,
            can_view_repair_guide=can_user_view_repair_guides(current_user),
        )
