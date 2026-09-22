# MuszakPro kozvetlen DB iras

## Cel

A MuszakPro ne Google Sheetbol legyen utolag beolvasva, hanem a foglalas,
torles es tomeges muvelet pillanataban irjon Supabase-be.

Az uj DB cel kulon schema:

- `muszakpro.bookings`
- `muszakpro.events`

A regi `Foglalasok` es `LOG` ful legfeljebb kompatibilitasi / atmeneti naplo.
Az uj fejlesztesnel a DB legyen az igazsag forrasa.

## Meglevo mukodes vedelme

Az atallas nem torheti el a jelenlegi MuszakPro mukodest.

- A regi Sheet iras egyelore megmarad.
- A DB iras plusz retegkent fut mellette.
- Ha a DB nem elerheto vagy hibazik, a foglalas / torles regi folyamata nem
  allhat meg emiatt.
- Elesben csak akkor szabad a Sheet fuggoseget kivenni, ha a DB iras es DB
  olvasas mar bizonyitottan stabil.

## Supabase letrehozas

Futtasd a Supabase SQL Editorban:

```text
docs/supabase_muszakpro_live.sql
```

Ez letrehozza:

- `muszakpro` schema
- `muszakpro.bookings`
- `muszakpro.events`
- olvasasi kompatibilitasi view-kat a regi public nevekre

Fontos Supabase beallitas:

```text
Project Settings -> API -> Exposed schemas
```

Itt add hozza:

```text
muszakpro
```

Enelkul a REST API nem fogja latni a kulon schemat.

## Apps Script beallitas

A Google Apps Script projektben a Project Settings -> Script properties alatt:

```text
SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
MUSZAKPRO_DB_ENABLED=TRUE
MUSZAKPRO_DB_SCHEMA=muszakpro
MUSZAKPRO_DB_TABLE=bookings
MUSZAKPRO_DB_EVENT_TABLE=events
```

## Apps Script fajlok

A `muszakpro/supabase_bridge_gs.txt` tartalmat add hozza az Apps Script
projekthez egy uj fajlkent, peldaul:

```text
SupabaseBridge.gs
```

A `muszakpro/Kod_gs_0712_0332.txt` exportalt backendben mar szerepelnek a
DB-hid hivasai:

- `muszakProDbBook(...)`
- `muszakProDbCancel(...)`
- `muszakProDbBulkBookRows(...)`
- `muszakProDbBulkCancelRows(...)`

Ezek a kovetkezoket irjak:

- aktualis foglalasi allapot: `muszakpro.bookings`
- muveleti tortenet: `muszakpro.events`

## Mit nem kell csinalni

Nem kell kulon Python / GitHub sync, ami a Google Sheetbol utolag behuzza az
adatot. Az csak visszatoltesre vagy egyszeri migraciora kellene, de az uj cel
nem ez.

Fontos: ez nem azt jelenti, hogy a mostani Sheet irast azonnal toroljuk. Csak
azt, hogy az uj adatfolyam nem utolagos Sheet importon alapul.

## Kovetkezo lepes

A MuszakPro felulet olvasasi reszeit is at kell vezetni DB-re, hogy a
kapacitas, foglaltsag es torles utan azonnal ugyanazt lassa, amit a DB-be ir.
