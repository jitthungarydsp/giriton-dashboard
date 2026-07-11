# JITT Kifli adatbazis rendrakas

Cel: a DB legyen atlathato, gyors es biztonsagosan bovitheto. Most meg sok tabla a `public`
schema alatt van, es keveredik a nyers adat, feldolgozott statisztika, invoice, PeopleForce es
robot adat. Eles tablat csak kulon jovahagyassal nevezunk at vagy torlunk.

## Javasolt retegek

| Reteg | Cel | Pelda |
| --- | --- | --- |
| `core` | Torzsadatok, kezzel es API-bol osszefesult stabil adatok | futar, raktar, auto |
| `raw` | Eredeti API/robot/sheet valaszok, minimalis atalakitassal | DSP detail JSON, Giriton shift raw |
| `stage` | Raw-bol bontott, tisztitott technikai tablak | route, shift, customer, attendance sorok |
| `mart` | Feluletre es riportokra optimalizalt osszesitesek | futar havi KPI, ceges KPI |
| `billing` | Elszamolas, bonusz, invoice es szerzodeses szabalyok | JITT invoice, bonus rules |
| `ops` | Mukodesi adatok, ertesites, task, PeopleForce | Discord route, dokumentum, reklamacio |

## Mostani tablak besorolasa

### Core

| Tabla | Javasolt szerep |
| --- | --- |
| `courier_master` | Futartorzzs: courier ID, nev, telefon, email, raktar |

### Raw

| Tabla | Forras | Megjegyzes |
| --- | --- | --- |
| `dsp_driver_detail_raw` | `fetch-drivers-detail` | Multbeli futar/detail API JSON |
| `dsp_drivers_live_raw` | `fetch-drivers` | Aktualis live DSP snapshot |
| `giriton_shifts_raw` | Giriton robot | Giriton muszakok |
| `giriton_attendance_raw` | Giriton attendance robot | Be- es kijelentkezes |
| `foglalasok_raw` | MuszakPro/Foglalasok sheet | MuszakPro foglalas raw |
| `dsp_vehicle_assignments` | `fetch-vehicle-assignments` | Auto kiosztas snapshot |
| `jitt_invoice_performance_bud1_raw` | Courier Hub performance | Uj elszamolasi raw, BUD1 |
| `jitt_invoice_performance_bud2_raw` | Courier Hub performance | Uj elszamolasi raw, BUD2 |

### Stage / calculated

| Tabla | Javasolt szerep |
| --- | --- |
| `dsp_order_arrivals` | Cimszintu erkezes/idoablak bontas |
| `dsp_route_delay_statistics` | Turaszintu keses statisztika |
| `dsp_route_distance_calculated` | Szamolt turatavolsag |
| `dsp_route_km_latest` | Live API-bol latott utolso km/tura allapot |
| `stg_jitt_invoice_performance_couriers` | Courier Hub performance futar bontas es szerzodeses mutatok |

### Mart / app

| Tabla | Javasolt szerep |
| --- | --- |
| `dsp_driver_month_summary` | Futar havi statisztika |
| `courier_card_stats` | Kiflis kartya gyors snapshot |

### Billing

| Tabla | Javasolt szerep |
| --- | --- |
| `jitt_invoice_imports` | Invoice import futasok |
| `jitt_invoice_summary_rows` | Invoice fo sorok |
| `jitt_invoice_route_rows` | Invoice route sorok |
| `jitt_invoice_final_routes` | Vegleges elszamolasi route sorok |
| `jitt_invoice_bonus_routes` | Bonus route sorok |
| `jitt_invoice_penalties` | Buntetesek |
| `jitt_invoice_contract_bonus_rules` | Szerzodeses bonusz szabalyok |
| `dsp_day_rates` | Naptipus dijak |
| `dsp_bonus_rates` | Szerzodeses bonusz/keses/turamegfeleles dijak |
| `dsp_band_rates` | Savos kereseti lehetoseg |
| `jitt_workbook_imports` | Excel import futas |
| `jitt_workbook_main_raw` | Excel felso/fo tabla raw |
| `jitt_workbook_detail_raw` | Excel reszletes tabla raw |

### Ops

| Tabla | Javasolt szerep |
| --- | --- |
| `discord_route_notifications` | Discord route ertesites es Kiflis utam alap |
| `peopleforce_documents` | Dokumentumok |
| `peopleforce_complaints` | Reklamaciok |
| `peopleforce_card_statuses` | Admin/futar visszajelzo lampa |

## Javasolt kovetkezo lepesek

1. Nem rombolo kommentek felvitele Supabase-ben: `docs/database_table_comments.sql`.
2. Uj tablat mar csak retegezett nevvel hozzunk letre:
   - `core_*`
   - `raw_*` vagy forras szerint `dsp_*_raw`, `giriton_*_raw`
   - `stage_*`
   - `mart_*`
   - `billing_*` vagy `jitt_invoice_*`
   - `ops_*`
3. A mostani tablakhoz keszitsunk `*_v1` vagy clean view-kat, es az oldalak ezeket olvassak.
4. Csak akkor nevezzunk at eles tablat, ha mar minden script es Streamlit oldal az uj view-kat hasznalja.

## Szabalyok mostantol

- Raw tabla nem torol adatot, csak upsertel vagy uj snapshotot tesz be.
- Feldolgozott/mart tabla ujraepitheto raw-bol.
- Invoice/billing tabla csak verziozott importtal frissuljon.
- Minden tabla tartalmazzon legalabb:
  - `created_at`
  - `updated_at` vagy `fetched_at`
  - forras azonosito (`source_name`, `import_id`, `batch_id`)
- Courier ID legyen az elso kapcsolo kulcs, ahol elerheto.
