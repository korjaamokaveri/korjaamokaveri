import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "vaihda-tama-myöhemmin-oikeasti-salaiseksi-avaimeksi")
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
    UPLOAD_FOLDER = "static/uploads/tickets"
    DB_PATH = os.environ.get("DB_PATH", "korjaamo_kaveri.db")
    DEBUG = os.environ.get("FLASK_DEBUG", "True") == "True"
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
    UPLOAD_FOLDER = "static/uploads/tickets"
