from datetime import datetime
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from google_client import open_spreadsheet

spreadsheet = open_spreadsheet(
    "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
)

def get_foglalasok_kulcsok():

    # A Foglalasok tabla kozos forras, ide nem irunk, csak olvasunk belole.
    ws = spreadsheet.worksheet("Foglalasok")

    values = ws.get_all_values()

    kulcsok = set()

    for row in values[1:]:

        if len(row) > 10:

            kulcs = row[10].strip()   # K oszlop

            if kulcs:
                kulcsok.add(kulcs)

    return kulcsok

def get_emails():

    ws_users = spreadsheet.worksheet("Felhasznalok")

    values = ws_users.get_all_values()

    emails = {}

    for row in values[1:]:

        if len(row) >= 4:

            nev = row[0].strip()
            email = row[3].strip()

            emails[nev] = email

    return emails
from datetime import datetime


def create_statistics():

    try:
        ws_stats = spreadsheet.worksheet("Statisztika")
    except:
        ws_stats = spreadsheet.add_worksheet(
            title="Statisztika",
            rows=1000,
            cols=20
        )

    try:
        ws_dsp = spreadsheet.worksheet("DSP_Attendance")
    except Exception:
        return "STAT_SKIPPED_DSP_ATTENDANCE_MISSING"

    dsp_rows = ws_dsp.get_all_values()

    today = datetime.today().date()

    month_start = today.replace(day=1)

    napok = {
        0: "Hétfő",
        1: "Kedd",
        2: "Szerda",
        3: "Csütörtök",
        4: "Péntek",
        5: "Szombat",
        6: "Vasárnap"
    }

    stats = {}

    for row in dsp_rows[1:]:

        try:

            if len(row) < 2:
                continue

            datum = row[0].strip()   # A oszlop
            nev = row[1].strip()     # B oszlop

            datum_obj = datetime.strptime(
                datum,
                "%Y-%m-%d"
            ).date()

            if datum_obj < month_start:
                continue

            if datum_obj > today:
                continue

            if nev not in stats:

                stats[nev] = {
                    "Hétfő": 0,
                    "Kedd": 0,
                    "Szerda": 0,
                    "Csütörtök": 0,
                    "Péntek": 0,
                    "Szombat": 0,
                    "Vasárnap": 0
                }

            nap = napok[datum_obj.weekday()]

            stats[nev][nap] += 1

        except Exception as e:
            print(e)

    rows = [[
        "Név",
        "Hétfő",
        "Kedd",
        "Szerda",
        "Csütörtök",
        "Péntek",
        "Szombat",
        "Vasárnap",
        "Összeg"
    ]]

    for nev in sorted(stats.keys()):

        hetfo = stats[nev]["Hétfő"]
        kedd = stats[nev]["Kedd"]
        szerda = stats[nev]["Szerda"]
        csutortok = stats[nev]["Csütörtök"]
        pentek = stats[nev]["Péntek"]
        szombat = stats[nev]["Szombat"]
        vasarnap = stats[nev]["Vasárnap"]

        osszeg = (
            hetfo * 13000 +
            kedd * 11000 +
            szerda * 11000 +
            csutortok * 13000 +
            pentek * 13000 +
            szombat * 13000 +
            vasarnap * 11000
        )

        rows.append([
            nev,
            hetfo,
            kedd,
            szerda,
            csutortok,
            pentek,
            szombat,
            vasarnap,
            osszeg
        ])

    ws_stats.clear()

    ws_stats.update(
        "A1",
        rows
    )

    return "STAT_OK"

def write_all_shifts(rows):

    worksheet = spreadsheet.worksheet("Giriton")

    # Régi adatok törlése (fejléc marad)
    worksheet.batch_clear(["A2:I10000"])

    emails = get_emails()
    foglalasok_kulcsok = get_foglalasok_kulcsok()

    new_rows = []

    for row in rows:

        datum = row[0]
        kezdes = row[1]
        vege = row[2]
        raktar = row[3]
        foglaltsag = row[4]
        foglalt =row[5]
        maximum =row[6]
        nev = row[7]

        email = emails.get(nev, "")

        kulcs = f"{datum}_{raktar}_{kezdes}_{email}"

        if kulcs in foglalasok_kulcsok:
            statusz = "GIRITON_OK"
        else:
            statusz = "NINCS_FOGLALAS"

        new_rows.append([
            datum,
            kezdes,
            vege,
            raktar,
            foglaltsag,
            foglalt,
            maximum,
            nev,
            email,
            kulcs,
            statusz
        ])

    worksheet.update(
    "A2:K",
    new_rows
    )

    return "OK"


def write_all_shifts_matrix(rows):
    worksheet = spreadsheet.worksheet("Töltöség")

    # Összes dátum
    dates = sorted(
        list(
            set(
                row[0]
                for row in rows
            )
        )
    )

    # műszak -> dátum -> maximum
    matrix = {}

    for row in rows:

        datum = row[0]
        kezdes = row[1]
        raktar = row[3]
        maximum = row[6]

        muszak = f"{raktar}_{kezdes}"

        if muszak not in matrix:
            matrix[muszak] = {}

        matrix[muszak][datum] = maximum

    output = []

    # fejléc
    header = ["muszak neve"]

    for datum in dates:

        datum_formazott = (
            datum[5:7]
            + "."
            + datum[8:10]
        )

        header.append(
            datum_formazott
        )

    output.append(
        header
    )

    # műszak sorok
    for muszak in sorted(
        matrix.keys()
    ):

        sor = [muszak]

        for datum in dates:

            sor.append(
                matrix[muszak].get(
                    datum,
                    0
                )
            )

        output.append(
            sor
        )

    # lezáró sor
    output.append(
        ["Befoglalt műszakok"]
    )

    worksheet.clear()

    worksheet.update(
        "A1",
        output
    )

    return "OK"

# -----------------------------------------------------------------
# ÚJ FÜGGVÉNY - BUD1_PROD2.0 és BUD2_PROD2.0 mátrix export
# FIGYELEM: Ez egy kész alap, a write_all_shifts() meghagyása mellett.
# A Robotból hívd meg: Write Open Shifts
# -----------------------------------------------------------------

OPEN_SHIFT_CHANGE_SHEET = "Open_Shift_Changes"
OPEN_SHIFT_CHANGE_HEADER = [
    "logged_at",
    "warehouse",
    "work_date",
    "shift",
    "previous_free",
    "current_free",
    "opened_free_slots",
]


def _safe_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _format_sheet_date(date_value):
    return f"{date_value[5:7]}.{date_value[8:10]}."


def _read_previous_open_shift_matrix(ws):
    values = ws.get_all_values()
    header_index = None

    for index, row in enumerate(values):
        if row and str(row[0]).strip().lower() in [
            "muszak neve",
            "műszak neve",
            "mĹ±szak neve",
        ]:
            header_index = index
            break

    if header_index is None:
        return {}

    header = values[header_index]
    date_by_column = {}

    for column_index, value in enumerate(header):
        if column_index < 3:
            continue

        value = str(value).strip()

        if value:
            date_by_column[column_index] = value

    previous = {}

    for row in values[header_index + 1:]:
        if not row:
            continue

        shift = str(row[0]).strip()

        if not shift or shift in [
            "Befoglalt műszakok",
            "Befoglalt mĹ±szakok",
        ]:
            break

        for column_index, sheet_date in date_by_column.items():
            value = row[column_index] if column_index < len(row) else ""
            previous[(shift, sheet_date)] = _safe_int(value)

    return previous


def _get_or_create_change_worksheet():
    try:
        ws = spreadsheet.worksheet(OPEN_SHIFT_CHANGE_SHEET)
    except:
        ws = spreadsheet.add_worksheet(
            title=OPEN_SHIFT_CHANGE_SHEET,
            rows=1000,
            cols=len(OPEN_SHIFT_CHANGE_HEADER),
        )

    if not ws.get_all_values():
        ws.update("A1", [OPEN_SHIFT_CHANGE_HEADER])

    return ws


def _append_open_shift_changes(change_rows):
    if not change_rows:
        return

    ws = _get_or_create_change_worksheet()
    ws.append_rows(
        change_rows,
        value_input_option="USER_ENTERED",
    )


def write_open_shifts(rows):
    if not rows:
        raise ValueError(
            "Nincs feldolgozhato muszaksor. A robot nem olvasott ki adatot a Giriton feluletrol."
        )

    warehouses = [
        ("BUD1","BUD1_PROD2.0"),
        ("BUD2","BUD2_PROD2.0")
    ]
    change_rows = []
    logged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summaries = []

    for warehouse, sheet_name in warehouses:

        try:
            ws = spreadsheet.worksheet(sheet_name)
        except:
            ws = spreadsheet.add_worksheet(
                title=sheet_name,
                rows=300,
                cols=40
            )

        previous_matrix = _read_previous_open_shift_matrix(ws)
        matrix = {}
        dates = sorted(set(r[0] for r in rows if r[3] == warehouse))

        for row in rows:

            if row[3] != warehouse:
                continue

            datum = row[0]
            kezdes = row[1]
            try:
                foglalt = int(row[5])
                maximum = int(row[6])
                szabad = max(maximum - foglalt, 0)
            except (TypeError, ValueError):
                szabad = 0

            key = f"{warehouse}_{kezdes}"

            matrix.setdefault(key,{})
            matrix[key][datum] = szabad

        if previous_matrix:
            for shift, shift_values in matrix.items():
                for datum, current_free in shift_values.items():
                    sheet_date = _format_sheet_date(datum)
                    previous_free = previous_matrix.get(
                        (shift, sheet_date),
                        0,
                    )

                    if current_free > previous_free:
                        change_rows.append([
                            logged_at,
                            warehouse,
                            datum,
                            shift,
                            previous_free,
                            current_free,
                            current_free - previous_free,
                        ])

        output = []

        # A-C oszlop kitöltetlen marad a dátumok előtt.
        # A sheetre A4-től írunk, így az első 3 sor üres lesz.
        header = ["műszak neve", "", ""]

        for d in dates:
            header.append(f"{d[5:7]}.{d[8:10]}.")

        output.append(header)

        def sort_key(x):
            return tuple(map(int, x.split("_")[1].split(":")))

        for shift in sorted(matrix.keys(), key=sort_key):

            row = [shift, "", ""]

            for d in dates:
                row.append(matrix[shift].get(d,0))

            output.append(row)

        output.append(["Befoglalt műszakok"])

        ws.clear()
        ws.update("A4", output)
        summaries.append(
            f"{sheet_name}: shifts={len(matrix)}, dates={len(dates)}, rows_written={len(output)}"
        )

    _append_open_shift_changes(change_rows)

    result = (
        "OK | "
        + " | ".join(summaries)
        + f" | changes_logged={len(change_rows)}"
    )
    print(result)

    return result
