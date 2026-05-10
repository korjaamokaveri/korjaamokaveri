from flask import render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import check_password_hash

from services.email_service import send_email
from services.user_service import (
    get_user_by_email,
    create_user,
    set_user_online,
    set_user_offline,
    update_user_password,
)
from services.password_reset_service import (
    create_password_reset_token,
    get_valid_password_reset_token,
    mark_password_reset_token_used,
    invalidate_user_reset_tokens,
)


def register_auth_routes(app):
    def empty_form_data():
        return {
            "email": "",
            "full_name": "",
            "phone": "",
            "address_line1": "",
            "postal_code": "",
            "city": "",
            "country": "Suomi",
            "customer_type": "private",
            "company_name": "",
            "vat_number": "",
            "accept_privacy": False,
        }

    @app.route("/register", methods=["GET", "POST"])
    def register():
        error = None
        success = None
        form_data = empty_form_data()

        if request.method == "POST":
            form_data["email"] = request.form.get("email", "").strip().lower()
            form_data["full_name"] = request.form.get("full_name", "").strip()
            form_data["phone"] = request.form.get("phone", "").strip()
            form_data["address_line1"] = request.form.get("address_line1", "").strip()
            form_data["postal_code"] = request.form.get("postal_code", "").strip()
            form_data["city"] = request.form.get("city", "").strip()
            form_data["country"] = request.form.get("country", "").strip() or "Suomi"
            form_data["customer_type"] = request.form.get("customer_type", "private").strip().lower()
            form_data["company_name"] = request.form.get("company_name", "").strip()
            form_data["vat_number"] = request.form.get("vat_number", "").strip()
            form_data["accept_privacy"] = request.form.get("accept_privacy") == "yes"

            password = request.form.get("password", "")
            password2 = request.form.get("password2", "")

            if form_data["customer_type"] not in {"private", "company"}:
                form_data["customer_type"] = "private"

            if (
                not form_data["email"]
                or not form_data["full_name"]
                or not form_data["phone"]
                or not form_data["address_line1"]
                or not form_data["postal_code"]
                or not form_data["city"]
                or not form_data["country"]
                or not password
                or not password2
            ):
                error = "Täytä kaikki pakolliset kentät."
            elif password != password2:
                error = "Salasanat eivät täsmää."
            elif len(password) < 6:
                error = "Salasanan pitää olla vähintään 6 merkkiä."
            elif not form_data["accept_privacy"]:
                error = "Hyväksy tietosuojaseloste."
            elif form_data["customer_type"] == "company" and not form_data["company_name"]:
                error = "Yritysasiakkaalle yrityksen nimi on pakollinen."
            elif get_user_by_email(form_data["email"]):
                error = "Tällä sähköpostilla on jo tili."
            else:
                create_user(
                    email=form_data["email"],
                    password=password,
                    full_name=form_data["full_name"],
                    phone=form_data["phone"],
                    address_line1=form_data["address_line1"],
                    postal_code=form_data["postal_code"],
                    city=form_data["city"],
                    country=form_data["country"],
                    customer_type=form_data["customer_type"],
                    company_name=form_data["company_name"],
                    vat_number=form_data["vat_number"],
                )
                success = "Rekisteröinti onnistui. Voit nyt kirjautua sisään."
                form_data = empty_form_data()

        return render_template(
            "register.html",
            error=error,
            success=success,
            **form_data,
        )

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = None
        email = ""

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            print(f"LOGIN DEBUG: email={email}")

            user = get_user_by_email(email)

            if not user:
                print("LOGIN DEBUG: käyttäjää ei löydy")
                error = "Käyttäjää ei löydy tietokannasta."

            elif not check_password_hash(user["password_hash"], password):
                print("LOGIN DEBUG: salasana väärä")
                error = "Salasana on väärä."

            else:
                session.clear()
                session["user_id"] = user["id"]
                session.permanent = True

                print(
                    f"LOGIN DEBUG: onnistui user_id={user['id']} "
                    f"is_admin={user['is_admin']} session_user_id={session.get('user_id')}"
                )

                set_user_online(user["id"])

                if user["is_admin"] == 1:
                    print("LOGIN DEBUG: ohjataan adminiin")
                    return redirect(url_for("admin.admin"))

                print("LOGIN DEBUG: ohjataan app_homeen")
                return redirect(url_for("app_home"))

        return render_template(
            "login.html",
            error=error,
            email=email,
        )
        
    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        error = None
        success = None
        email = ""

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()

            if not email:
                error = "Anna sähköposti."
            else:
                user = get_user_by_email(email)

                if user:
                    token = create_password_reset_token(user["id"])
                    reset_link = url_for("reset_password", token=token, _external=True)

                    email_sent = send_email(
                        to_email=email,
                        subject="Korjaamo Kaveri - salasanan vaihto",
                        body=f"""Hei,

Voit vaihtaa Korjaamo Kaveri -salasanasi tästä linkistä:

{reset_link}

Linkki on voimassa yhden tunnin.

Jos et pyytänyt salasanan vaihtoa, voit jättää tämän viestin huomiotta.

Terveisin,
Korjaamo Kaveri
"""
                    )

                    print(f"PASSWORD RESET: email_sent={email_sent} email={email}")
                else:
                    print(f"PASSWORD RESET: käyttäjää ei löytynyt {email}")

                success = "Jos sähköposti löytyy järjestelmästä, salasanan vaihtolinkki on lähetetty."

                return render_template(
                    "forgot_password.html",
                    error=error,
                    success=success,
                    email="",
                )

        return render_template(
            "forgot_password.html",
            error=error,
            success=success,
            email=email,
        )

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    def reset_password(token):
        error = None
        success = None

        token_row = get_valid_password_reset_token(token)

        if not token_row:
            return render_template(
                "reset_password.html",
                error="Linkki on vanhentunut tai virheellinen.",
                success=None,
                token_valid=False,
                token=token,
            )

        if request.method == "POST":
            password = request.form.get("password", "")
            password2 = request.form.get("password2", "")

            if not password or not password2:
                error = "Täytä kaikki kentät."
            elif password != password2:
                error = "Salasanat eivät täsmää."
            elif len(password) < 6:
                error = "Salasanan pitää olla vähintään 6 merkkiä."
            else:
                update_user_password(token_row["user_id"], password)
                invalidate_user_reset_tokens(token_row["user_id"])
                mark_password_reset_token_used(token)

                return render_template(
                    "reset_password.html",
                    error=None,
                    success="Salasana vaihdettu onnistuneesti. Voit nyt kirjautua sisään.",
                    token_valid=False,
                    token=token,
                )

        return render_template(
            "reset_password.html",
            error=error,
            success=success,
            token_valid=True,
            token=token,
        )

    @app.route("/logout", methods=["GET"])
    def logout():
        user_id = session.get("user_id")
        if user_id:
            set_user_offline(user_id)

        session.clear()
        return redirect(url_for("login"))

    @app.route("/api/register", methods=["POST"])
    def api_register():
        data = request.get_json(silent=True) or {}

        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        password2 = data.get("password2", "")
        full_name = data.get("full_name", "").strip()
        phone = data.get("phone", "").strip()
        address_line1 = data.get("address_line1", "").strip()
        postal_code = data.get("postal_code", "").strip()
        city = data.get("city", "").strip()
        country = data.get("country", "").strip() or "Suomi"
        customer_type = data.get("customer_type", "private").strip().lower()
        company_name = data.get("company_name", "").strip()
        vat_number = data.get("vat_number", "").strip()
        accept_privacy = bool(data.get("accept_privacy", False))

        if customer_type not in {"private", "company"}:
            customer_type = "private"

        if (
            not email
            or not password
            or not password2
            or not full_name
            or not phone
            or not address_line1
            or not postal_code
            or not city
            or not country
        ):
            return jsonify({"success": False, "message": "Täytä kaikki pakolliset kentät."}), 400

        if password != password2:
            return jsonify({"success": False, "message": "Salasanat eivät täsmää."}), 400

        if len(password) < 6:
            return jsonify({"success": False, "message": "Salasanan pitää olla vähintään 6 merkkiä."}), 400

        if not accept_privacy:
            return jsonify({"success": False, "message": "Hyväksy tietosuojaseloste."}), 400

        if customer_type == "company" and not company_name:
            return jsonify({"success": False, "message": "Yritysasiakkaalle yrityksen nimi on pakollinen."}), 400

        if get_user_by_email(email):
            return jsonify({"success": False, "message": "Tällä sähköpostilla on jo tili."}), 409

        create_user(
            email=email,
            password=password,
            full_name=full_name,
            phone=phone,
            address_line1=address_line1,
            postal_code=postal_code,
            city=city,
            country=country,
            customer_type=customer_type,
            company_name=company_name,
            vat_number=vat_number,
        )

        return jsonify({"success": True, "message": "Rekisteröinti onnistui."}), 201

    @app.route("/api/login", methods=["POST"])
    def api_login():
        data = request.get_json(silent=True) or {}

        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email or not password:
            return jsonify({"success": False, "message": "Sähköposti ja salasana ovat pakollisia."}), 400

        user = get_user_by_email(email)

        if not user:
            return jsonify({"success": False, "message": "Käyttäjää ei löydy tietokannasta."}), 401

        if not check_password_hash(user["password_hash"], password):
            return jsonify({"success": False, "message": "Salasana on väärä."}), 401

        session["user_id"] = user["id"]
        set_user_online(user["id"])

        return jsonify({
            "success": True,
            "message": "Kirjautuminen onnistui.",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "is_admin": user["is_admin"],
            },
        }), 200

    @app.route("/api/forgot-password", methods=["POST"])
    def api_forgot_password():
        data = request.get_json(silent=True) or {}
        email = data.get("email", "").strip().lower()

        if not email:
            return jsonify({"success": False, "message": "Anna sähköposti."}), 400

        user = get_user_by_email(email)

        if user:
            token = create_password_reset_token(user["id"])
            reset_link = url_for("reset_password", token=token, _external=True)

            send_email(
                to_email=email,
                subject="Korjaamo Kaveri - salasanan vaihto",
                body=f"""Hei,

Voit vaihtaa Korjaamo Kaveri -salasanasi tästä linkistä:

{reset_link}

Linkki on voimassa yhden tunnin.

Jos et pyytänyt salasanan vaihtoa, voit jättää tämän viestin huomiotta.

Terveisin,
Korjaamo Kaveri
"""
            )

        return jsonify({
            "success": True,
            "message": "Jos sähköposti löytyy järjestelmästä, salasanan vaihtolinkki on lähetetty.",
        }), 200

    @app.route("/api/reset-password", methods=["POST"])
    def api_reset_password():
        data = request.get_json(silent=True) or {}

        token = data.get("token", "").strip()
        password = data.get("password", "")
        password2 = data.get("password2", "")

        if not token or not password or not password2:
            return jsonify({"success": False, "message": "Täytä kaikki kentät."}), 400

        if password != password2:
            return jsonify({"success": False, "message": "Salasanat eivät täsmää."}), 400

        if len(password) < 6:
            return jsonify({"success": False, "message": "Salasanan pitää olla vähintään 6 merkkiä."}), 400

        token_row = get_valid_password_reset_token(token)
        if not token_row:
            return jsonify({"success": False, "message": "Linkki on vanhentunut tai virheellinen."}), 400

        update_user_password(token_row["user_id"], password)
        invalidate_user_reset_tokens(token_row["user_id"])
        mark_password_reset_token_used(token)

        return jsonify({"success": True, "message": "Salasana vaihdettu onnistuneesti."}), 200

    @app.route("/api/logout", methods=["POST"])
    def api_logout():
        user_id = session.get("user_id")

        if user_id:
            set_user_offline(user_id)

        session.clear()

        return jsonify({"success": True, "message": "Uloskirjautuminen onnistui."}), 200
