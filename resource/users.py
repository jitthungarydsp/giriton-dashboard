import json
import secrets
from datetime import datetime


USERS_FILE = "data/users.json"


def load_users():

    with open(
        "data/users.json",
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def save_users(data):

    with open(
        "data/users.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=4
        )


def generate_password():

    return secrets.token_urlsafe(8)


def create_user(
    username,
    courier_id,
    role
):

    data = load_users()

    password = generate_password()

    new_user = {

        "username": username,

        "password": password,

        "role": role,

        "courierId": courier_id,

        "active": True,

        "token": "",

        "createdAt":
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

    }

    data["users"].append(
        new_user
    )

    save_users(
        data
    )

    return password


def reset_password(
    username
):

    data = load_users()

    password = generate_password()

    for user in data["users"]:

        if (
            user["username"]
            ==
            username
        ):

            user["password"] = password

            break

    save_users(
        data
    )

    return password


def update_role(
    username,
    role
):

    data = load_users()

    for user in data["users"]:

        if (
            user["username"]
            ==
            username
        ):

            user["role"] = role

            break

    save_users(
        data
    )


def toggle_active(
    username,
    active
):

    data = load_users()

    for user in data["users"]:

        if (
            user["username"]
            ==
            username
        ):

            user["active"] = active

            break

    save_users(
        data
    )
    
def update_trainer(
    username,
    trainer
):

    data = load_users()

    for user in data["users"]:

        if user["username"] == username:

            user["trainer"] = trainer

            break

    save_users(data)


def delete_user(
    username
):

    data = load_users()

    data["users"] = [

        u

        for u in data["users"]

        if u["username"] != username

    ]

    save_users(data)