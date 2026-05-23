import os
import resend


resend.api_key = os.getenv("RESEND_API_KEY")


def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        resend.Emails.send({
            "from": os.getenv("MAIL_FROM"),
            "to": to_email,
            "subject": subject,
            "text": body,
        })

        print(f"EMAIL OK: {to_email}")
        return True

    except Exception as e:
        print(f"EMAIL ERROR: {type(e).__name__}: {e}")
        return False
