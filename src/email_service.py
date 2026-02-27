import os
import smtplib
from email.message import EmailMessage


def _get_smtp_settings() -> dict:
    host = os.getenv("SMTP_HOST", "").strip()
    port = os.getenv("SMTP_PORT", "").strip()
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    from_email = os.getenv("SMTP_FROM_EMAIL", "").strip()
    use_tls_raw = os.getenv("SMTP_USE_TLS", "true").strip().lower()

    # Backward-compatible fallback for previous Resend-specific variable names
    if not host:
        host = os.getenv("RESEND_SMTP_HOST", "smtp.resend.com").strip()
    if not port:
        port = os.getenv("RESEND_SMTP_PORT", "587").strip()
    if not username:
        username = os.getenv("RESEND_SMTP_USERNAME", "resend").strip()
    if not password:
        password = os.getenv("RESEND_SMTP_PASSWORD", "").strip()
    if not from_email:
        from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@resend.dev").strip()

    return {
        "host": host,
        "port": int(port or "587"),
        "username": username,
        "password": password,
        "from_email": from_email,
        "use_tls": use_tls_raw not in {"0", "false", "no"},
    }


def is_email_ready() -> bool:
    settings = _get_smtp_settings()
    return bool(settings["password"] and settings["from_email"])


def send_decision_email(
    recipient_email: str,
    recipient_name: str,
    member_id: str,
    decision: str,
    review_note: str = "",
) -> tuple[bool, str]:
    settings = _get_smtp_settings()

    if not recipient_email:
        return False, "Missing recipient email"

    if not is_email_ready():
        return False, "SMTP not configured"

    decision_upper = decision.strip().upper()
    note_text = review_note.strip() or "No additional note provided."

    subject = f"VIP Lounge Application {decision_upper}"
    body_text = (
        f"Hello {recipient_name},\n\n"
        f"Your VIP lounge application has been {decision_upper}.\n"
        f"Member ID: {member_id}\n"
        f"Review note: {note_text}\n\n"
        "Thank you."
    )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings["from_email"]
    message["To"] = recipient_email
    message.set_content(body_text)

    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=15) as server:
            if settings["use_tls"]:
                server.starttls()
            server.login(settings["username"], settings["password"])
            server.send_message(message)
        return True, "Email sent"
    except Exception as exc:
        return False, f"Email failed: {exc}"
