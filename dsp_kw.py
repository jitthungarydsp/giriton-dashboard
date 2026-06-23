import requests
import gspread
from dsp_common_kw import hu_time
from datetime import datetime, date, timedelta
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    r"C:\Giriton\girition-a89bab5e91bc.json",
    scopes=SCOPES
)

client = gspread.authorize(creds)

spreadsheet = client.open_by_key(
    "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
)


def load_dsp_attendance(datum):

    url = (
        f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
        f"fetch-attendance/JIT/{datum}"
        f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
    )

    response = requests.get(url)

    data = response.json()

    rows = []

    for courier in data.get("couriers", []):

        nev = courier.get("courierName", "")
        raktar = courier.get("warehouseName", "")

        for shift in courier.get("shifts", []):

            shift_start = datetime.fromisoformat(
                shift["shiftStart"].replace("Z", "+00:00")
            )

            shift_end = datetime.fromisoformat(
                shift["shiftEnd"].replace("Z", "+00:00")
            )

            available = shift.get("availableForShiftSince")

            belepes = ""
            korabban = ""

            if available:

                available_dt = datetime.fromisoformat(
                    available.replace("Z", "+00:00")
                )

                belepes = available_dt.strftime("%H:%M:%S")

                korabban = round(
                    (shift_start - available_dt).total_seconds() / 60,
                    1
                )

            rows.append([
                data["date"],
                nev,
                raktar,
                shift.get("shiftName", ""),
                shift_start.strftime("%H:%M"),
                shift_end.strftime("%H:%M"),
                belepes,
                korabban
            ])

    return rows


def load_month_attendance():

    try:
        ws = spreadsheet.worksheet("DSP_Attendance")
    except:
        ws = spreadsheet.add_worksheet(
            title="DSP_Attendance",
            rows=50000,
            cols=20
        )

    all_rows = [[
        "Dátum",
        "Név",
        "Raktár",
        "Műszak",
        "Kezdés",
        "Vége",
        "Bejelentkezett",
        "Korábban (perc)"
    ]]

    today = date.today()

    current = today.replace(day=1)

    while current <= today:

        datum = current.strftime("%Y-%m-%d")

        print(f"Lekérés: {datum}")

        try:

            napi_rows = load_dsp_attendance(datum)

            all_rows.extend(napi_rows)

            print(f"  -> {len(napi_rows)} sor")

        except Exception as e:

            print(f"HIBA {datum}: {e}")

        current += timedelta(days=1)

    ws.clear()

    ws.update(
        "A1",
        all_rows
    )

    print(
        f"Kész. {len(all_rows)-1} sor feltöltve."
    )

    return "OK"


if __name__ == "__main__":

    result = load_month_attendance()

    print(result)