import os

DB_PATH = "korjaamo_kaveri.db"

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-this")

ADMIN_EMAIL = "ville_salovaara@hotmail.com"


# 🔥 STRIPE
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_BASIC = os.getenv("STRIPE_PRICE_BASIC")


# 🌍 APP URL (tärkeä Stripe redirecteille)
BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")