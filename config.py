import os

class Config:
    DB_PATH = os.getenv("DB_PATH", "korjaamo_kaveri.db")

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "dev-secret-change-this"
    )

    ADMIN_EMAIL = os.getenv(
        "ADMIN_EMAIL",
        "ville_salovaara@hotmail.com"
    )

    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Stripe
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
    STRIPE_PRICE_BASIC = os.getenv("STRIPE_PRICE_BASIC")

    # Renderissä tämä pitää olla oikea osoite
    BASE_URL = os.getenv(
        "BASE_URL",
        "https://korjaamokaveri.onrender.com"
    )
