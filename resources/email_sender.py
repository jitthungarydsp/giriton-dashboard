import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import streamlit as st


def get_setting(name, default=""):
    value = os.getenv(name)
    if value not in (None, ""):
        return str(value)
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = default
    return str(value or default)


def parse_bool(value, default=False):
    text = str(value or "").strip().casefold()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def validate_email(value):
    email = str(value or "").strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Érvénytelen e-mail-cím.")
    return email


def smtp_config():
    host = get_setting("SMTP_HOST")
    username = get_setting("SMTP_USERNAME")
    password = get_setting("SMTP_PASSWORD")
    from_email = get_setting("SMTP_FROM_EMAIL", username)
    if not host or not username or not password or not from_email:
        raise RuntimeError(
            "Hiányos SMTP-beállítás. SMTP_HOST, SMTP_USERNAME, "
            "SMTP_PASSWORD és SMTP_FROM_EMAIL szükséges."
        )
    use_ssl = parse_bool(get_setting("SMTP_USE_SSL"), default=False)
    port_default = "465" if use_ssl else "587"
    return {
        "host": host,
        "port": int(get_setting("SMTP_PORT", port_default)),
        "username": username,
        "password": password,
        "from_email": from_email,
        "from_name": get_setting("SMTP_FROM_NAME", "Giriton"),
        "use_ssl": use_ssl,
        "use_starttls": parse_bool(
            get_setting("SMTP_USE_STARTTLS"), default=not use_ssl
        ),
    }


def build_login_message(recipient, username, temporary_password):
    recipient = validate_email(recipient)
    login_url = get_setting("APP_LOGIN_URL")
    config = smtp_config()
    message = EmailMessage()
    message["Subject"] = "Giriton belépési adatok"
    message["From"] = formataddr((config["from_name"], config["from_email"]))
    message["To"] = recipient
    login_line = f"Belépési oldal: {login_url}\n" if login_url else ""
    message.set_content(
        "Kedves Futár!\n\n"
        "Elkészültek a Giriton belépési adataid.\n\n"
        f"Felhasználónév: {username}\n"
        f"Ideiglenes jelszó: {temporary_password}\n"
        f"{login_line}\n"
        "https://giriton-courier-pwa.onrender.com/"
        "A jelszót ne továbbítsd másnak.\n\n"
        "Üdvözlettel:Jitt Hungary\n"
    )
    return message, config


def new_bill(recipient, username):
    recipient = validate_email(recipient)
    login_url = get_setting("APP_LOGIN_URL")
    config = smtp_config()
    message = EmailMessage()
    message["Subject"] = "Új elszámolásod érkezett !"
    message["From"] = formataddr((config["from_name"], config["from_email"]))
    message["To"] = recipient
    login_line = f"Belépési oldal: {login_url}\n" if login_url else ""
    message.set_content(
        "Kedves Futár!\n\n"
        "Elkészültek a Giriton belépési adataid.\n\n"
        f"Felhasználónév: {username}\n"
        f"Ideiglenes jelszó: {temporary_password}\n"
        f"{login_line}\n"
        "A jelszót ne továbbítsd másnak.\n\n"
        "Üdvözlettel:Jitt Hungary KFT\n"
    )
    return message, config


def send_login_credentials(recipient, username, temporary_password):
    message, config = build_login_message(
        recipient,
        username,
        temporary_password,
    )
    context = ssl.create_default_context()
    if config["use_ssl"]:
        with smtplib.SMTP_SSL(
            config["host"], config["port"], timeout=30, context=context
        ) as smtp:
            smtp.login(config["username"], config["password"])
            smtp.send_message(message)
    else:
        with smtplib.SMTP(config["host"], config["port"], timeout=30) as smtp:
            smtp.ehlo()
            if config["use_starttls"]:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(config["username"], config["password"])
            smtp.send_message(message)
    return {
        "recipient": validate_email(recipient),
        "subject": str(message["Subject"]),
    }
