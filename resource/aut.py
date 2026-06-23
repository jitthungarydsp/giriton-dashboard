import json
import secrets

from streamlit_cookies_manager import EncryptedCookieManager

COOKIE_NAME = "dsp_token"


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


def authenticate(
    username,
    password
):

    data = load_users()

    for user in data["users"]:

        if (
            user["username"] == username
            and
            user["password"] == password
            and
            user.get(
                "active",
                True
            )
        ):

            return user

    return None


def create_token():

    return secrets.token_hex(
        32
    )


def save_token(
    username
):

    data = load_users()

    token = create_token()

    for user in data["users"]:

        if (
            user["username"]
            ==
            username
        ):

            user["token"] = token

            break

    save_users(
        data
    )

    return token


def login_by_token(
    token
):

    if not token:
        return None

    data = load_users()

    for user in data["users"]:

        if (
            user.get(
                "token"
            )
            ==
            token
        ):

            return user

    return None


def logout(
    username
):

    data = load_users()

    for user in data["users"]:

        if (
            user["username"]
            ==
            username
        ):

            user["token"] = ""

    save_users(
        data
    )