import requests
from dsp_common_kw import local_today

from datetime import timedelta
from google_client import open_spreadsheet

spreadsheet = open_spreadsheet(
    "1s6M4qSBp7KjGsEtrD8oNCs5Opq7-xRDJ1fupCQLMABE"
)


def load_drivers():

    try:
        ws = spreadsheet.worksheet("DSP_Drivers")
    except:
        ws = spreadsheet.add_worksheet(
            title="DSP_Drivers",
            rows=50000,
            cols=20
        )

    rows = [[
        "date",
        "driver_id",
        "name",
        "contact_email",
        "contact_number",
        "warehouse_name"
    ]]

    today = local_today()
    current = today.replace(day=1)
    
    #today = date.today()

    #current = today

    while current <= today:

        datum = current.strftime("%Y-%m-%d")

        print(f"Lekérés: {datum}")

        url = (
            f"https://uftplslamjbbhlozsygo.supabase.co/functions/v1/"
            f"fetch-drivers-by-date/JIT/{datum}"
            f"?organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc"
        )

        try:

            response = requests.get(url)
            data = response.json()

            for driver in data["drivers"]:

                personal = driver.get(
                    "personal_info",
                    {}
                )

                rows.append([
                    datum,
                    driver.get("driver_id", ""),
                    personal.get("name", ""),
                    personal.get("contact_email", ""),
                    personal.get("contact_number", ""),
                    personal.get("warehouse_name", "")
                ])

        except Exception as e:

            print(
                f"HIBA {datum}: {e}"
            )

        current += timedelta(days=1)

    ws.clear()

    ws.update(
        "A1",
        rows
    )

    print(
        f"{len(rows)-1} sor feltöltve."
    )

    return "OK"
