import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr
from string import Formatter

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


def first_setting(*names, default=""):
    for name in names:
        value = get_setting(name)
        if str(value or "").strip():
            return str(value)
    return default


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
    host = first_setting("SMTP_HOST", "EMAIL_HOST", "MAIL_HOST", "SMTP_SERVER")
    username = first_setting("SMTP_USERNAME", "SMTP_USER", "EMAIL_USERNAME", "EMAIL_USER", "MAIL_USERNAME", "MAIL_USER")
    password = first_setting("SMTP_PASSWORD", "SMTP_PASS", "EMAIL_PASSWORD", "EMAIL_PASS", "MAIL_PASSWORD", "MAIL_PASS")
    from_email = first_setting("SMTP_FROM_EMAIL", "EMAIL_FROM", "MAIL_FROM", "FROM_EMAIL", default=username)

    if not host or not username or not password or not from_email:
        missing = []
        if not host:
            missing.append("SMTP_HOST")
        if not username:
            missing.append("SMTP_USERNAME")
        if not password:
            missing.append("SMTP_PASSWORD")
        if not from_email:
            missing.append("SMTP_FROM_EMAIL")
        raise RuntimeError(
            "Hiányos SMTP-beállítás. Hiányzik: " + ", ".join(missing) + "."
        )

    use_ssl = parse_bool(get_setting("SMTP_USE_SSL"), default=False)
    port_default = "465" if use_ssl else "587"

    return {
        "host": host,
        "port": int(first_setting("SMTP_PORT", "EMAIL_PORT", "MAIL_PORT", default=port_default)),
        "username": username,
        "password": password,
        "from_email": from_email,
        "from_name": first_setting("SMTP_FROM_NAME", "EMAIL_FROM_NAME", "MAIL_FROM_NAME", default="JITT"),
        "use_ssl": use_ssl,
        "use_starttls": parse_bool(
            first_setting("SMTP_USE_STARTTLS", "EMAIL_USE_STARTTLS", "MAIL_USE_STARTTLS"),
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


DEFAULT_EMAIL_TEMPLATES = {
    "new_settlement": {
        "name": "Új elszámolás érkezett",
        "subject": "Új elszámolásod érkezett",
        "body": (
            "Kedves {courier_name}!\n\n"
            "Új elszámolásod érkezett a JITT felületén.\n"
            "Hónap: {month}\n\n"
            "Itt tudod megnézni:\n{login_url}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "settlement_accepted": {
        "name": "Elszámolás elfogadva",
        "subject": "Elszámolás elfogadva",
        "body": (
            "Kedves {courier_name}!\n\n"
            "Rögzítettük, hogy elfogadtad az elszámolásodat.\n"
            "Hónap: {month}\n"
            "Összeg: {amount_huf}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "tig_accepted": {
        "name": "TIG elfogadva",
        "subject": "TIG elfogadva",
        "body": (
            "Kedves {courier_name}!\n\n"
            "Rögzítettük, hogy elfogadtad a TIG-et.\n"
            "Hónap: {month}\n"
            "TIG végösszeg: {amount_huf}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "document_uploaded": {
        "name": "Új dokumentum",
        "subject": "Új dokumentumod érkezett",
        "body": (
            "Kedves {courier_name}!\n\n"
            "Új dokumentum érkezett a JITT felületén.\n"
            "Típus: {document_type}\n"
            "Hónap: {month}\n"
            "Dokumentum: {document_title}\n\n"
            "Itt tudod megnézni:\n{login_url}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "complaint_response": {
        "name": "Reklamáció válasz",
        "subject": "Válasz érkezett a reklamációdra",
        "body": (
            "Kedves {courier_name}!\n\n"
            "Válasz érkezett a reklamációdra.\n"
            "Hónap: {month}\n\n"
            "Válasz:\n{admin_message}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "payment_rejected": {
        "name": "Kifizetés elutasítva / visszanyitva",
        "subject": "Kifizetés státusza módosult",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A kifizetésed státusza módosult.\n"
            "Hónap: {month}\n\n"
            "Megjegyzés:\n{status_note}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "free_text": {
        "name": "Szabad szöveges e-mail",
        "subject": "JITT üzenet",
        "body": (
            "Kedves {courier_name}!\n\n"
            "{free_text}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_settlement_missing": {
        "name": "Státusz - elszámolásra vár",
        "subject": "Elszámolás előkészítés alatt",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi elszámolásod még előkészítés alatt van.\n"
            "Amint elérhető lesz, a PWA felületen látni fogod.\n\n"
            "Belépés:\n{login_url}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_settlement_acceptance_waiting": {
        "name": "Státusz - elszámolás elfogadásra vár",
        "subject": "Elfogadásra vár az elszámolásod",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi elszámolásod elfogadásra vár.\n"
            "Kérjük, nézd át és fogadd el a PWA felületen.\n\n"
            "Belépés:\n{login_url}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_tig_missing": {
        "name": "Státusz - TIG-re vár",
        "subject": "A TIG előkészítés alatt van",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi TIG még előkészítés alatt van.\n"
            "Amint elkészül, a PWA felületen fogod látni.\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_tig_acceptance_waiting": {
        "name": "Státusz - TIG elfogadásra vár",
        "subject": "Elfogadásra vár a TIG-ed",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi TIG-ed elfogadásra vár.\n"
            "Kérjük, nézd át és fogadd el a PWA felületen.\n\n"
            "Belépés:\n{login_url}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_invoice_upload_waiting": {
        "name": "Státusz - számlafeltöltésre vár",
        "subject": "Számlafeltöltés szükséges",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi folyamatod számlafeltöltésre vár.\n"
            "Kérjük, töltsd fel a számlát a PWA felületen.\n"
            "Várt összeg: {amount_huf}\n\n"
            "Belépés:\n{login_url}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_invoice_check_waiting": {
        "name": "Státusz - számlaellenőrzésre vár",
        "subject": "A számlád ellenőrzés alatt van",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi számlád ellenőrzés alatt van.\n"
            "Ha szükség lesz javításra, külön jelezni fogjuk.\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_complaint_open": {
        "name": "Státusz - bejelentések",
        "subject": "Nyitott bejelentésed van",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi folyamatodban nyitott bejelentés szerepel.\n"
            "Amint válasz érkezik rá, értesítünk.\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_salary_advance_open": {
        "name": "Státusz - új fizetés előleg",
        "subject": "Fizetés előleg igénylésed nyitva van",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A fizetés előleg igénylésed nyitott státuszban van.\n"
            "A feldolgozás állapotát a PWA felületen tudod követni.\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_payment_waiting": {
        "name": "Státusz - kifizetésre vár",
        "subject": "Kifizetésre vár a havi folyamatod",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi folyamatod kifizetésre vár.\n"
            "Aktuális összeg: {amount_huf}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
    "status_paid": {
        "name": "Státusz - kifizetve",
        "subject": "A havi folyamatod lezárva",
        "body": (
            "Kedves {courier_name}!\n\n"
            "A {month} havi folyamatod lezárva, kifizetett státuszban van.\n"
            "Végösszeg: {amount_huf}\n\n"
            "Üdvözlettel:\nJITT"
        ),
    },
}


def _safe_format(value, variables):
    class SafeDict(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return str(value or "").format_map(SafeDict({key: str(item or "") for key, item in variables.items()}))


def template_variables(template_text):
    fields = []
    for _literal, field_name, _format_spec, _conversion in Formatter().parse(str(template_text or "")):
        if field_name and field_name not in fields:
            fields.append(field_name)
    return fields


def render_template_text(subject, body, variables):
    return _safe_format(subject, variables), _safe_format(body, variables)


def build_custom_message(recipient, subject, body):
    recipient = validate_email(recipient)
    config = smtp_config()

    message = EmailMessage()
    message["Subject"] = str(subject or "").strip() or "JITT üzenet"
    message["From"] = formataddr((config["from_name"], config["from_email"]))
    message["To"] = recipient
    message.set_content(str(body or "").strip())
    return message, config


def send_custom_email(recipient, subject, body):
    message, config = build_custom_message(recipient, subject, body)
    send_message(message, config)
    return {
        "recipient": validate_email(recipient),
        "subject": str(message["Subject"]),
    }


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
