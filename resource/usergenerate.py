import json
import random
import string
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets"
]

creds = Credentials.from_service_account_file(
    r"C:\Giriton\girition-a89bab5e91bc.json",
    scopes=SCOPES
)

client = gspread.authorize(creds)

spreadsheet = client.open_by_key(
    "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
)

ws = spreadsheet.worksheet(
    "DSP_Drivers"
)

rows = ws.get_all_values()

users = []
trainer = "trainer_name"
processed = set()
token = ""

for row in rows[1:]:

    courier_id = row[1]
    courier_name = row[2]

    if courier_id in processed:
        continue

    processed.add(courier_id)

    password = "".join(
        random.choices(
            string.ascii_letters +
            string.digits,
            k=8
        )
    )

    users.append({

        "username": courier_name,
        
        "trainer": trainer,

        "password": password,

        "role": "user",

        "courierId": int(courier_id),

        "active": True,
        
        "token" : ""

    })

with open(
    "data/users.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        {"users": users},
        f,
        ensure_ascii=False,
        indent=4
    )

print(
    f"{len(users)} user létrehozva."
)