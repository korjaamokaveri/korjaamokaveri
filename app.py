from flask import Flask, render_template_string

from db_init import init_db
from services.diagnostics_service import diagnose
from services.user_service import make_user_admin
from routes.admin_routes import admin_bp
from routes.admin_repair_guide_routes import admin_repair_guides_bp
from routes.main_routes import register_main_routes
from routes.auth_routes import register_auth_routes
from routes.history_routes import register_history_routes
from utils.auth import get_current_user
from utils.config import Config
from dotenv import load_dotenv
load_dotenv()

LOGOUT_PAGE = """
<!doctype html>
<html lang="fi">
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="2;url=/login">
    <title>Kirjauduttu ulos</title>
</head>
<body>
    <h1>Kirjauduttu ulos</h1>
    <p>Olet kirjautunut ulos onnistuneesti.</p>
    <p><a href="/login">Kirjaudu uudelleen</a></p>

    <script>
        setTimeout(function () {
            window.location.href = "/login";
        }, 2000);
    </script>
</body>
</html>
"""


def create_app():
    init_db()

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    app.register_blueprint(admin_repair_guides_bp)
    app.register_blueprint(admin_bp)

    register_main_routes(app)
    register_auth_routes(app)
    register_history_routes(app)

    @app.context_processor
    def inject_user():
        return dict(current_user=get_current_user())
        
    @app.route("/")
    def home():
        return "Korjaamo Kaveri toimii 🚀"     

    @app.route("/logged-out")
    def logged_out():
        return render_template_string(LOGOUT_PAGE)

    return app

def cli_test():
    print("=== Korjaamo Kaveri CLI-testi ===")
    code = input("Anna vikakoodi: ").strip()
    make = input("Anna merkki: ").strip()
    model = input("Anna malli: ").strip()
    engine = input("Anna moottori (voi jättää tyhjäksi): ").strip()
    symptoms = input("Kuvaa oireet: ").strip()

    result = diagnose(code, make, model, symptoms, engine)

    print("\n--- TULOS ---")
    if not result["success"]:
        print(result["message"])
        return

    print(f"Vikakoodi: {result['fault_code']}")
    print(f"Otsikko: {result['title']}")
    print(f"Kuvaus: {result['description']}")
    print(
        f"Ajoneuvo: {result['vehicle']['make']} "
        f"{result['vehicle']['model']} "
        f"{result['vehicle']['engine']}".strip()
    )

    if result["symptom_notes"]:
        print("\nOirehavainnot:")
        for note in result["symptom_notes"]:
            print(f"- {note}")

    if result["vehicle_notes"]:
        print("\nAjoneuvokohtaiset huomiot:")
        for note in result["vehicle_notes"]:
            print(f"- {note}")

    print("\nTodennäköiset syyt:")
    for cause in result["possible_causes"]:
        print(f"- {cause['name']} (score: {cause['score']}): {cause['description']}")

    print("\nTestausjärjestys:")
    for step in result["test_steps"]:
        print(f"{step['order']}. {step['title']} – {step['description']} [{step['tools']}]")

    print("\nHuom: Tämä on automaattinen arvio oman tietokannan perusteella.")


app = create_app()


app = create_app()


@app.route("/health")
def health():
    return "OK", 200


if __name__ == "__main__":
    print("API käynnissä osoitteessa http://127.0.0.1:5000")
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=app.config["DEBUG"]
    )
