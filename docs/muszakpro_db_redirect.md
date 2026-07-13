# MuszakPro atvezetes sajat DB-re

## Cel

A helyi MuszakPro jelenleg a regi Google Sheet `Foglalasok` fulbe ir.
Az elso stabil atvezetes dual-write:

- a regi Google Sheet iras megmarad, hogy a MuszakPro felulet ne torjon el,
- minden uj foglalas es torles bekerul Supabase-be is,
- a DB-ben a torles nem fizikai torles, hanem `status = CANCELLED`.

## Supabase tabla

Futtasd a Supabase SQL Editorban:

```text
docs/supabase_muszakpro_live.sql
```

Ez letrehozza / kiegesziti:

- `raw_muszakpro_bookings`
- `ops_muszakpro_events`

Ha a regi `foglalasok_raw` tabla meg letezik, az SQL atemeli az aktiv adatokat az uj prefixelt tablanev ala.

## Apps Script beallitas

A Google Apps Script projektben a Project Settings -> Script properties alatt:

```text
SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
MUSZAKPRO_DB_ENABLED=TRUE
MUSZAKPRO_DB_TABLE=raw_muszakpro_bookings
MUSZAKPRO_DB_EVENT_TABLE=ops_muszakpro_events
```

## Apps Script fajlok

A `muszakpro/supabase_bridge_gs.txt` tartalmat add hozza az Apps Script projekthez egy uj fajlkent, peldaul:

```text
SupabaseBridge.gs
```

A `muszakpro/Kod_gs_0712_0332.txt` exportalt backendbe bekerultek a hid hivasai:

- `muszakProDbBook(...)`
- `muszakProDbCancel(...)`
- `muszakProDbBulkBookRows(...)`
- `muszakProDbBulkCancelRows(...)`

## Python / Streamlit oldal

A `resources/foglalasok_db.py` most mar eloszor a `raw_muszakpro_bookings` tablat keresi.
Ha nincs ilyen tabla, visszaesik a regi `foglalasok_raw` tablara.

Az olvasas az uj tablanal kiszuri a `CANCELLED` statuszu sorokat.

## Kovetkezo lepes

Ha a dual-write nehany napig stabil:

1. A MuszakPro olvasasait at lehet vezetni DB-re.
2. A `beo` kapacitasokat is kulon DB tablaba kell vinni.
3. A regi Google Sheet mar csak backup / export lesz.
