import json
import secrets
import unicodedata
from copy import deepcopy
from datetime import datetime

from resources.security import hash_password

USERS_FILE = "data/users.json"


def load_users():
    with open(USERS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_users(data):
    with open(USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def generate_password():
    return secrets.token_urlsafe(8)


def normalize_name(value):
    text = unicodedata.normalize("NFKD", str(value or "").strip().casefold())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.split())


def normalize_courier_id(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except (TypeError, ValueError):
        return text


def is_protected_user(user):
    username = normalize_name(user.get("username"))
    role = normalize_name(user.get("role"))
    return (
        role == "admin"
        or username == "admin"
        or username == normalize_name("Bagoly Zoltán")
    )


def create_user(username, courier_id, role, trainer=""):
    data = load_users()
    username = str(username or "").strip()
    if not username:
        raise ValueError("A név megadása kötelező.")

    for user in data.get("users", []):
        if normalize_name(user.get("username")) == normalize_name(username):
            raise ValueError("Ilyen nevű felhasználó már létezik.")

    password = generate_password()
    data.setdefault("users", []).append(
        {
            "username": username,
            "password": password,
            "passwordHash": hash_password(password),
            "role": role,
            "courierId": int(courier_id),
            "trainer": trainer,
            "active": True,
            "token": "",
            "createdAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    save_users(data)
    return password


def reset_password(username):
    data = load_users()
    password = generate_password()

    for user in data.get("users", []):
        if user.get("username") == username:
            user["password"] = password
            user["passwordHash"] = hash_password(password)
            user["token"] = ""
            user["passwordUpdatedAt"] = datetime.now().isoformat(timespec="seconds")
            save_users(data)
            return password

    raise ValueError("A felhasználó nem található.")


def reset_password_and_send(username, recipient_email, send_function):
    data = load_users()
    selected_index = None

    for index, user in enumerate(data.get("users", [])):
        if user.get("username") == username:
            selected_index = index
            break

    if selected_index is None:
        raise ValueError("A felhasználó nem található.")

    previous_user = deepcopy(data["users"][selected_index])
    password = generate_password()
    user = data["users"][selected_index]
    user["password"] = password
    user["passwordHash"] = hash_password(password)
    user["token"] = ""
    user["passwordUpdatedAt"] = datetime.now().isoformat(timespec="seconds")
    save_users(data)

    try:
        result = send_function(recipient_email, username, password)
    except Exception:
        rollback_data = load_users()
        for index, current_user in enumerate(rollback_data.get("users", [])):
            if current_user.get("username") == username:
                rollback_data["users"][index] = previous_user
                break
        save_users(rollback_data)
        raise

    final_data = load_users()
    for current_user in final_data.get("users", []):
        if current_user.get("username") == username:
            current_user["credentialEmail"] = str(recipient_email).strip()
            current_user["credentialEmailSentAt"] = datetime.now().isoformat(
                timespec="seconds"
            )
            break
    save_users(final_data)
    return result


def build_courier_master_sync_preview(courier_rows):
    data = load_users()
    users = data.get("users", [])
    users_by_id = {
        normalize_courier_id(user.get("courierId")): user
        for user in users
        if normalize_courier_id(user.get("courierId"))
    }

    preview = []
    for row in courier_rows:
        courier_id = normalize_courier_id(row.get("courier_id"))
        courier_name = str(row.get("courier_name") or "").strip()
        if not courier_id or not courier_name:
            continue

        existing = users_by_id.get(courier_id)
        if existing and is_protected_user(existing):
            action = "Védett – változatlan"
        elif existing:
            action = "Frissítés + jelszó reset"
        else:
            action = "Új felhasználó"

        preview.append(
            {
                "courier_id": int(courier_id),
                "courier_name": courier_name,
                "active": True if row.get("active") is None else bool(row.get("active")),
                "existing_username": str(existing.get("username") or "") if existing else "",
                "action": action,
            }
        )
    return preview


def sync_users_from_courier_master(courier_rows, *, reset_existing=True):
    data = load_users()
    users = data.setdefault("users", [])
    users_by_id = {
        normalize_courier_id(user.get("courierId")): user
        for user in users
        if normalize_courier_id(user.get("courierId"))
    }

    result = {
        "created": 0,
        "updated": 0,
        "reset": 0,
        "protected": 0,
        "skipped": 0,
        "passwords": [],
    }
    now = datetime.now().isoformat(timespec="seconds")

    for row in courier_rows:
        courier_id = normalize_courier_id(row.get("courier_id"))
        courier_name = str(row.get("courier_name") or "").strip()
        if not courier_id or not courier_name:
            result["skipped"] += 1
            continue

        active = True if row.get("active") is None else bool(row.get("active"))
        existing = users_by_id.get(courier_id)

        if existing:
            if is_protected_user(existing):
                result["protected"] += 1
                continue

            existing["username"] = courier_name
            existing["courierId"] = int(courier_id)
            existing["active"] = active
            existing.setdefault("role", "user")
            existing.setdefault("trainer", "")
            existing["token"] = ""
            existing["updatedAt"] = now

            if reset_existing:
                password = generate_password()
                existing["password"] = password
                existing["passwordHash"] = hash_password(password)
                existing["passwordUpdatedAt"] = now
                result["reset"] += 1
                result["passwords"].append(
                    {
                        "courier_id": int(courier_id),
                        "username": courier_name,
                        "password": password,
                    }
                )
            result["updated"] += 1
            continue

        password = generate_password()
        new_user = {
            "username": courier_name,
            "password": password,
            "passwordHash": hash_password(password),
            "role": "user",
            "courierId": int(courier_id),
            "trainer": "",
            "active": active,
            "token": "",
            "createdAt": now,
            "passwordUpdatedAt": now,
        }
        users.append(new_user)
        users_by_id[courier_id] = new_user
        result["created"] += 1
        result["passwords"].append(
            {
                "courier_id": int(courier_id),
                "username": courier_name,
                "password": password,
            }
        )

    save_users(data)
    return result


def update_role(username, role):
    data = load_users()
    for user in data.get("users", []):
        if user.get("username") == username:
            user["role"] = role
            break
    save_users(data)


def toggle_active(username, active):
    data = load_users()
    for user in data.get("users", []):
        if user.get("username") == username:
            user["active"] = active
            break
    save_users(data)


def update_trainer(username, trainer):
    data = load_users()
    for user in data.get("users", []):
        if user.get("username") == username:
            user["trainer"] = trainer
            break
    save_users(data)


def delete_user(username):
    data = load_users()
    data["users"] = [
        user for user in data.get("users", [])
        if user.get("username") != username
    ]
    save_users(data)