import os

import gspread
from google.oauth2.service_account import Credentials


SHEETS = [
    "1Ax3TFDGVHZKiRbJby6YKWoptPJznwQk8WZ7__-zTfvs",
    "1hd-rCwJcEeFCVRQ0wdt35URlYKuw89iVwGWgp5gNNwE",
    "1D2lqZsNoUPdL3c-8Wj2ytKGVeiRqgerFM5Uo5gTZj8k",
]

credentials = Credentials.from_service_account_file(
    os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ],
)

client = gspread.authorize(credentials)

for spreadsheet_id in SHEETS:
    print("\n" + "=" * 80)
    print("Spreadsheet ID:", spreadsheet_id)

    spreadsheet = client.open_by_key(spreadsheet_id)
    print("Cím:", spreadsheet.title)

    for worksheet in spreadsheet.worksheets():
        print(
            f"- {worksheet.title} | gid={worksheet.id} | "
            f"sor={worksheet.row_count} | oszlop={worksheet.col_count}"
        )

        values = worksheet.get_all_values()

        for row in values[:8]:
            print(row)