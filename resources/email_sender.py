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


def app_login_url():
    fallback = "https://giriton-courier-pwa.onrender.com/"
    for name in ("PWA_LOGIN_URL", "APP_LOGIN_URL", "PUBLIC_PWA_URL", "PUBLIC_APP_URL"):
        value = get_setting(name).strip()
        if value and "example.com" not in value.casefold():
            return value
    return fallback


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
        "from_name": get_setting("SMTP_FROM_NAME", "JITT"),
        "use_ssl": use_ssl,
        "use_starttls": parse_bool(
            get_setting("SMTP_USE_STARTTLS"),
            default=not use_ssl,
        ),
    }


def build_login_message(recipient, username, password):
    recipient = validate_email(recipient)
    login_url = app_login_url()
    config = smtp_config()

    message = EmailMessage()
    message["Subject"] = "Jitt belépési adatok"
    message["From"] = formataddr((config["from_name"], config["from_email"]))
    message["To"] = recipient

    message.set_content(
        "Kedves Futár!\n\n"
        "Az alábbiak a Jitt belépési adataid:\n\n"
        f"Felhasználónév: {username}\n"
        f"Jelszó: {password}\n"
        f"Belépési oldal: {login_url}\n\n"
        "A jelszót ne továbbítsd másnak.\n\n"
        "Üdvözlettel:\n"
        "Jitt Hungary Kft.\n"
    )

    return message, config


def build_new_bill_message(recipient, username):
    recipient = validate_email(recipient)
    login_url = app_login_url()
    config = smtp_config()

    message = EmailMessage()
    message["Subject"] = "Új elszámolásod érkezett!"
    message["From"] = formataddr((config["from_name"], config["from_email"]))
    message["To"] = recipient

    message.set_content(
        "Kedves Futár!\n\n"
        "Új elszámolásod érkezett a Jitt rendszerben.\n\n"
        f"Felhasználónév: {username}\n"
        f"Belépési oldal: {login_url}\n\n"
        "Üdvözlettel:\n"
        "Jitt Hungary Kft.\n"
    )

    return message, config


def build_new_document_message(
    recipient,
    courier_name="",
    document_type="",
    document_month="",
    title="",
):
    recipient = validate_email(recipient)
    login_url = app_login_url()
    config = smtp_config()

    labels = {
        "settlement": "elszámolás",
        "tig": "TIG",
        "invoice": "számla",
        "complaint_response": "reklamációs válasz",
    }
    clean_type = str(document_type or "").strip()
    label = labels.get(clean_type, "dokumentum")
    clean_month = str(document_month or "").strip()[:7]
    clean_title = str(title or label).strip()
    clean_name = str(courier_name or "Futár").strip()

    message = EmailMessage()
    message["Subject"] = "Új dokumentumod érkezett"
    message["From"] = formataddr((config["from_name"], config["from_email"]))
    message["To"] = recipient

    message.set_content(
        f"Kedves {clean_name}!\n\n"
        f"Új {label} dokumentumod érkezett a Jitt rendszerben.\n"
        f"Hónap: {clean_month or '-'}\n"
        f"Dokumentum: {clean_title}\n\n"
        f"Az új felületen itt tudod megnézni:\n{login_url}\n\n"
        "Üdvözlettel:\n"
        "Jitt Hungary Kft.\n"
    )

    return message, config


def build_invoice_payment_message(
    recipient,
    courier_name="",
    document_month="",
    invoice_number="",
    amount_huf="",
):
    recipient = validate_email(recipient)
    login_url = app_login_url()
    config = smtp_config()

    clean_name = str(courier_name or "Futár").strip()
    clean_month = str(document_month or "").strip()[:7]
    clean_invoice_number = str(invoice_number or "").strip()
    clean_amount = str(amount_huf or "").strip()

    message = EmailMessage()
    message["Subject"] = "Számlád kifizetésre kerül"
    message["From"] = formataddr((config["from_name"], config["from_email"]))
    message["To"] = recipient

    details = []
    if clean_month:
        details.append(f"Hónap: {clean_month}")
    if clean_invoice_number:
        details.append(f"Számlaszám: {clean_invoice_number}")
    if clean_amount:
        details.append(f"Összeg: {clean_amount}")

    detail_text = "\n".join(details)
    if detail_text:
        detail_text = f"\n{detail_text}\n"

    message.set_content(
        f"Kedves {clean_name}!\n\n"
        "A beküldött számládat admin oldalon elfogadtuk, "
        "a számla kifizetésre kerül.\n"
        f"{detail_text}\n"
        f"A folyamatot az új felületen itt tudod megnézni:\n{login_url}\n\n"
        "Üdvözlettel:\n"
        "Jitt Hungary Kft.\n"
    )

    return message, config


def send_message(message, config):
    context = ssl.create_default_context()

    if config["use_ssl"]:
        with smtplib.SMTP_SSL(
            config["host"],
            config["port"],
            timeout=30,
            context=context,
        ) as smtp:
            smtp.login(config["username"], config["password"])
            smtp.send_message(message)
    else:
        with smtplib.SMTP(
            config["host"],
            config["port"],
            timeout=30,
        ) as smtp:
            smtp.ehlo()
            if config["use_starttls"]:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(config["username"], config["password"])
            smtp.send_message(message)


def send_login_credentials(recipient, username, password):
    message, config = build_login_message(
        recipient,
        username,
        password,
    )
    send_message(message, config)

    return {
        "recipient": validate_email(recipient),
        "subject": str(message["Subject"]),
    }


def send_new_bill_notification(recipient, username):
    message, config = build_new_bill_message(
        recipient,
        username,
    )
    send_message(message, config)

    return {
        "recipient": validate_email(recipient),
        "subject": str(message["Subject"]),
    }


def send_new_document_notification(
    recipient,
    courier_name="",
    document_type="",
    document_month="",
    title="",
):
    message, config = build_new_document_message(
        recipient,
        courier_name=courier_name,
        document_type=document_type,
        document_month=document_month,
        title=title,
    )
    send_message(message, config)

    return {
        "recipient": validate_email(recipient),
        "subject": str(message["Subject"]),
    }


def send_invoice_payment_notification(
    recipient,
    courier_name="",
    document_month="",
    invoice_number="",
    amount_huf="",
):
    message, config = build_invoice_payment_message(
        recipient,
        courier_name=courier_name,
        document_month=document_month,
        invoice_number=invoice_number,
        amount_huf=amount_huf,
    )
    send_message(message, config)

    return {
        "recipient": validate_email(recipient),
        "subject": str(message["Subject"]),
    }
