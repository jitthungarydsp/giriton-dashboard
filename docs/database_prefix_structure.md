# Prefixelt DB struktura

Cel: a Supabase `public` listaja legyen atlathato ugy, hogy az eles tablakat nem
nevezzuk at azonnal. Elso lepesben alias view-kat hozunk letre prefixelt nevekkel.

## Prefix szabaly

| Prefix | Jelentes | Mit tartalmaz |
| --- | --- | --- |
| `core_` | torzsadat | futar, raktar, auto, stabil azonosito |
| `raw_` | nyers forrasadat | API, robot, Google Sheet, Excel valasz minimalis atalakitassal |
| `stg_` | feldolgozott technikai reteg | raw-bol bontott route, cim, shift, attendance sorok |
| `mart_` | feluleti/riport reteg | gyors dashboard es KPI osszesites |
| `bill_` | elszamolas | invoice, route dijazas, bonusz, buntetes |
| `cfg_` | konfiguracio | dijtabla, szerzodeses szabaly, savok |
| `ops_` | mukodesi adatok | Discord, PeopleForce, task, reklamacio |

## Javasolt nevek

### Core

| Uj nev | Mostani forras | Cel |
| --- | --- | --- |
| `core_couriers` | `courier_master` | futartorzzs |

### Raw

| Uj nev | Mostani forras | Cel |
| --- | --- | --- |
| `raw_dsp_driver_detail` | `dsp_driver_detail_raw` | fetch-drivers-detail nyers JSON |
| `raw_dsp_live_drivers` | `dsp_drivers_live_raw` | fetch-drivers live snapshot |
| `raw_dsp_vehicle_assignments` | `dsp_vehicle_assignments` | auto kiosztas |
| `raw_giriton_shifts` | `giriton_shifts_raw` | Giriton muszakok |
| `raw_giriton_attendance` | `giriton_attendance_raw` | Giriton be-/kijelentkezes |
| `raw_muszakpro_bookings` | `foglalasok_raw` | MuszakPro/Foglalasok |
| `raw_jitt_invoice_perf_bud1` | `jitt_invoice_performance_bud1_raw` | Courier Hub performance BUD1 |
| `raw_jitt_invoice_perf_bud2` | `jitt_invoice_performance_bud2_raw` | Courier Hub performance BUD2 |
| `raw_jitt_workbook_imports` | `jitt_workbook_imports` | workbook import futas |
| `raw_jitt_workbook_main` | `jitt_workbook_main_raw` | workbook fo tabla raw |
| `raw_jitt_workbook_detail` | `jitt_workbook_detail_raw` | workbook reszletes raw |

### Stage

| Uj nev | Mostani forras | Cel |
| --- | --- | --- |
| `stg_dsp_order_arrivals` | `dsp_order_arrivals` | cimszintu idoablak/erkezes |
| `stg_dsp_route_delay` | `dsp_route_delay_statistics` | route keses statisztika |
| `stg_dsp_route_distance` | `dsp_route_distance_calculated` | szamolt route tavolsag |
| `stg_dsp_route_km_latest` | `dsp_route_km_latest` | live km/tura allapot |

### Mart

| Uj nev | Mostani forras | Cel |
| --- | --- | --- |
| `mart_dsp_driver_month` | `dsp_driver_month_summary` | havi futar KPI |
| `mart_courier_card_stats` | `courier_card_stats` | Kiflis kartya gyors stat |

### Billing

| Uj nev | Mostani forras | Cel |
| --- | --- | --- |
| `bill_jitt_invoice_imports` | `jitt_invoice_imports` | invoice import futas |
| `bill_jitt_invoice_summary` | `jitt_invoice_summary_rows` | invoice fo sorok |
| `bill_jitt_invoice_routes` | `jitt_invoice_route_rows` | invoice route sorok |
| `bill_jitt_invoice_final_routes` | `jitt_invoice_final_routes` | vegleges route elszamolas |
| `bill_jitt_invoice_bonus_routes` | `jitt_invoice_bonus_routes` | bonusz route sorok |
| `bill_jitt_invoice_penalties` | `jitt_invoice_penalties` | buntetesek |
| `bill_jitt_contract_bonus_rules` | `jitt_invoice_contract_bonus_rules` | szerzodeses bonusz szabalyok |

### Config

| Uj nev | Mostani forras | Cel |
| --- | --- | --- |
| `cfg_dsp_day_rates` | `dsp_day_rates` | nap tipus dijak |
| `cfg_dsp_bonus_rates` | `dsp_bonus_rates` | keses/turamegfeleles bonusz dijak |
| `cfg_dsp_band_rates` | `dsp_band_rates` | savos dijak |

### Ops

| Uj nev | Mostani forras | Cel |
| --- | --- | --- |
| `ops_discord_route_notifications` | `discord_route_notifications` | route ertesites |
| `ops_peopleforce_documents` | `peopleforce_documents` | dokumentumok |
| `ops_peopleforce_complaints` | `peopleforce_complaints` | reklamaciok |
| `ops_peopleforce_card_statuses` | `peopleforce_card_statuses` | futar/admin visszajelzo lampak |

## Fontos

- Ezek elso korben view-k, nem uj adatos tablak.
- Az app es a robotok tovabbra is hasznalhatjak a regi neveket.
- Ha mar minden stabil, kesobb donthetunk tenyleges tabla-atnevezesrol vagy kulon schema-krol.
