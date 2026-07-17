from io import BytesIO

import pandas as pd
import requests

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from resources.supabase_raw import (
    get_supabase_config,
    raise_for_supabase_error,
)


CSV_PATH = Path(__file__).resolve().parent / "target_reserve.csv"


def normalize_courier_id(value):
    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    # Excelből származó 12345.0 alak javítása
    if text.endswith(".0"):
        text = text[:-2]

    # Szóközök és nem törhető szóközök eltávolítása
    text = text.replace(" ", "").replace("\u00a0", "")

    # Magyar formátum esetén
    text = text.replace(",", ".")

    try:
        return int(float(text))
    except (TypeError, ValueError):
        print(f"Kihagyott USERNUMBER: {value!r}")
        return None

def normalize_amount(value):
    if pd.isna(value):
        return 0

    text = str(value).strip()

    if not text or text.upper() in {
        "#VALUE!",
        "#N/A",
        "NAN",
        "NONE",
    }:
        return 0

    text = (
        text
        .replace("Ft", "")
        .replace("HUF", "")
        .replace("\u00a0", "")
        .replace(" ", "")
    )

    # Például: 125 000 vagy 125.000
    if "," not in text and text.count(".") == 1:
        before, after = text.split(".")

        if len(after) == 3:
            text = before + after

    text = text.replace(",", ".")

    try:
        return int(round(float(text)))
    except (TypeError, ValueError):
        print(f"Hibás CT_Z_FT érték, 0 lesz: {value!r}")
        return 0

def read_sheet_rows():
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"Nem található a CSV fájl: {CSV_PATH}"
        )

    raw_df = pd.read_csv(
        CSV_PATH,
        header=None,
    )

    header_row = None

    for index, row in raw_df.iterrows():
        normalized = {
            str(value).strip().upper().replace(" ", "")
            for value in row.tolist()
        }

        if "USERNUMBER" in normalized:
            header_row = index
            break

    if header_row is None:
        raise RuntimeError(
            "Nem található a USERNUMBER fejléc."
        )

    df = pd.read_csv(
        CSV_PATH,
        header=header_row,
    )

    user_number_column = next(
        column
        for column in df.columns
        if str(column).strip().upper().replace(" ", "")
        == "USERNUMBER"
    )

    balance_column = next(
        column
        for column in df.columns
        if str(column).strip().upper().replace(" ", "")
        == "CT_Z_FT"
    )

    rows = []

    for _, row in df.iterrows():
        courier_id = normalize_courier_id(
            row.get(user_number_column)
        )

        if courier_id is None:
            continue

        balance = normalize_amount(
            row.get(balance_column)
        )

        rows.append({
            "courier_id": courier_id,
            "opening_balance_huf": balance,
            "current_balance_huf": balance,
            "insurance_active": True,
        })

    return rows


def upload_rows(rows):
    config = get_supabase_config()

    response = requests.post(
        f"{config['url']}/rest/v1/courier_target_reserve",
        headers={
            "apikey": config["key"],
            "Authorization": f"Bearer {config['key']}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        params={
            "on_conflict": "courier_id",
        },
        json=rows,
        timeout=60,
    )

    raise_for_supabase_error(response)


def main():
    rows = read_sheet_rows()

    print(f"Beolvasott futárok: {len(rows)}")

    if not rows:
        raise RuntimeError("Nincs importálható adat.")

    upload_rows(rows)

    print("Import sikeresen befejezve.")


if __name__ == "__main__":
    main()