import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=SCOPES
)

client = gspread.authorize(creds)

SPREADSHEET_ID = "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"

def write_shift(datum, kezdes, vege, raktar, foglaltsag, nev):

    sh = client.open_by_key(SPREADSHEET_ID)

    ws = sh.get_worksheet_by_id(1954978251)

    ws.append_row([
        datum,
        kezdes,
        vege,
        raktar,
        foglaltsag,
        nev
    ])