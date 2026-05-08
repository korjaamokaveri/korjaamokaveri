import os

# Yhteensopivuus vanhan koodin kanssa
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

# Base URL
BASE_URL = os.getenv(
    "BASE_URL",
    "https://korjaamokaveri.onrender.com"
)


class Config:
    DB_PATH = DB_PATH
    SECRET_KEY = SECRET_KEY
    ADMIN_EMAIL = ADMIN_EMAIL
    DEBUG = DEBUG

    STRIPE_SECRET_KEY = STRIPE_SECRET_KEY
    STRIPE_WEBHOOK_SECRET = STRIPE_WEBHOOK_SECRET
    STRIPE_PRICE_BASIC = STRIPE_PRICE_BASIC

    BASE_URL = BASE_URL
