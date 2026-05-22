import os
import smtplib
import ssl
from email.message import EmailMessage


def send_email(to_email: str, subject: str, body: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "").strip()
    mail_from = os.getenv("MAIL_FROM", smtp_user).strip()

    if not smtp_host or not smtp_user or not smtp_password or not mail_from:
        print("EMAIL ERROR: SMTP-asetukset puuttuvat.")
        print(f"SMTP_HOST set: {bool(smtp_host)}")
        print(f"SMTP_PORT: {smtp_port}")
        print(f"SMTP_USER set: {bool(smtp_user)}")
        print(f"SMTP_PASSWORD set: {bool(smtp_password)}")
        print(f"MAIL_FROM set: {bool(mail_from)}")
        return False

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if smtp_port == 465:
            context = ssl.create_default_context()

            with smtplib.SMTP_SSL(
                smtp_host,
                smtp_port,
                context=context,
                timeout=5
            ) as server:
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

        else:
            with smtplib.SMTP(
                smtp_host,
                smtp_port,
                timeout=5
            ) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()

                server.login(smtp_user, smtp_password)
                server.send_message(msg)

        print(f"EMAIL OK: Lähetetty osoitteeseen {to_email}")
        return True

    except Exception as e:
        print(f"EMAIL ERROR: {type(e).__name__}: {e}")
        return False
