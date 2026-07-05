import os
import smtplib
from collections.abc import Mapping
from email.message import EmailMessage

import streamlit as st


def _read_secret(name, default=None):
    try:
        if name in st.secrets:
            return st.secrets.get(name)

        email_secrets = st.secrets.get("email", {})
        if isinstance(email_secrets, Mapping) and name in email_secrets:
            return email_secrets.get(name)
    except Exception:
        pass

    return os.getenv(name, default)


def send_email(to_address, subject, body):
    host = str(_read_secret("SMTP_HOST", "") or "").strip()
    port = int(_read_secret("SMTP_PORT", "587") or 587)
    username = str(_read_secret("SMTP_USER", "") or "").strip()
    password = str(_read_secret("SMTP_PASSWORD", "") or "")
    from_address = str(_read_secret("SMTP_FROM", username) or "").strip()
    use_ssl = str(_read_secret("SMTP_USE_SSL", "false") or "").lower() == "true"
    use_tls = str(_read_secret("SMTP_USE_TLS", "true") or "").lower() == "true"

    if not host or not from_address:
        raise RuntimeError(
            "Hianyzik az SMTP beallitas. Add meg legalabb az SMTP_HOST es SMTP_FROM/SMTP_USER ertekeket."
        )

    message = EmailMessage()
    message["From"] = from_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
