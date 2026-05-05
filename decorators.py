from functools import wraps
from flask import redirect, session, request

from services.user_service import get_user_by_id


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user_by_id(user_id)


def login_redirect():
    return redirect(f"/login?next={request.path}")


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not get_current_user():
            return login_redirect()
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
            return login_redirect()

        if user["is_admin"] != 1:
            return redirect("/app")

        return func(*args, **kwargs)

    return wrapper


def base_system_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = get_current_user()

        if not user:
            return login_redirect()

        if user["is_admin"] == 1:
            return func(*args, **kwargs)

        if user["subscription_status"] != "active":
            return redirect("/subscription-required")

        return func(*args, **kwargs)

    return wrapper