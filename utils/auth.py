from functools import wraps

from flask import redirect, session, url_for

from services.user_service import get_user_by_id


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def is_admin():
    user = get_current_user()
    return user and user["is_admin"] == 1


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            return redirect(url_for("login"))
        if user["is_admin"] != 1:
            return redirect(url_for("app_home"))
        return func(*args, **kwargs)
    return wrapper