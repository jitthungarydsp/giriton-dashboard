from datetime import datetime
from google_client import open_spreadsheet

spreadsheet = open_spreadsheet(
    "1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg"
)

def get_foglalasok_kulcsok():

    ws = spreadsheet.worksheet("FoglalasokGiriton")

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
    worksheet.batch_clear(["A2:K10000"])

    emails = get_emails()
    foglalasok_kulcsok = get_foglalasok_kulcsok()

    new_rows = []

    for row in rows:

        datum = row[0]
        kezdes = row[1]
        vege = row[2]
        raktar = row[3]
        foglaltsag = row[4]
        if len(row) >= 8:
            foglalt = row[5]
            maximum = row[6]
            nev = row[7]
        else:
            foglalt = ""
            maximum = ""
            nev = row[5]

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

