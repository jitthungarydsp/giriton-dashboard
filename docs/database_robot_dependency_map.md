# Robotok es DB tabla-fuggosegek

Ez a dokumentum azt mutatja, hogy a jelenlegi robotok es scriptek mely tablakhoz
nyulnak. A prefixelt DB-atallas elott ezek a pontok a fontosak.

## GitHub Actions

### `giriton-robots.yml`

| Job | Script/robot | Fo tablak |
| --- | --- | --- |
| `jitt_invoice` | `scripts/load_jitt_invoice_workbook.py` | `jitt_invoice_*`, `jitt_workbook_*` |
| `folgaltsag` | `folgaltsag_github.robot` | Google Sheet, majd `foglalasok_raw`/Giriton helper |
| `girition` | `girition_github.robot`, `update_shift_reconciliation.py`, `scripts/refresh_shift_comparison.py` | `giriton_shifts_raw`, `foglalasok_raw`, `ops_shift_comparison` |
| `attendance` | `giriton_attendance_github.robot` | `giriton_attendance_raw` |
| `dsp` | `dsp.py`, `scripts/build_courier_card_stats.py` | `dsp_*`, `courier_master`, `courier_card_stats` |

### `dsp-live-drivers.yml`

| Script | Fo tablak |
| --- | --- |
| `scripts/load_drivers_live_raw.py` | `dsp_drivers_live_raw`, `dsp_route_km_latest` |

### `discord-route-monitor.yml`

| Script | Fo tablak |
| --- | --- |
| `scripts/discord_route_monitor.py` | `discord_route_notifications` |

### `jitt-invoice-performance.yml`

| Script | Fo tablak |
| --- | --- |
| `scripts/load_jitt_invoice_performance_raw.py` | `jitt_invoice_performance_bud1_raw`, `jitt_invoice_performance_bud2_raw` |
| `scripts/build_jitt_invoice_performance_stage.py` | `stg_jitt_invoice_performance_couriers` |

## Tabla-nev atvezetes

| Regi nev | Uj nev | Erintett kod |
| --- | --- | --- |
| `courier_master` | `core_couriers` | `load_courier_master.py`, `courier_master_db.py`, `foglalasok_db.py`, `giriton_shifts_db.py` |
| `dsp_driver_detail_raw` | `raw_dsp_driver_detail` | `load_driver_detail_raw.py`, `supabase_raw.py`, `calculate_route_distances.py`, `dsp_refresh_all.py` |
| `dsp_attendance_raw` | `raw_dsp_attendance` | `load_driver_detail_raw.py`, `dsp_attendance_raw.py`, `dsp_refresh_all.py` |
| `dsp_drivers_live_raw` | `raw_dsp_live_drivers` | `load_drivers_live_raw.py` |
| `dsp_route_km_latest` | `stg_dsp_route_km_latest` | `load_drivers_live_raw.py` |
| `dsp_vehicle_assignments` | `raw_dsp_vehicle_assignments` | `load_vehicle_assignments.py`, `supabase_raw.py` |
| `giriton_shifts_raw` | `raw_giriton_shifts` | `giriton_shifts_db.py`, `load_giriton_shifts_from_sheet.py` |
| `giriton_attendance_raw` | `raw_giriton_attendance` | `giriton_attendance_db.py`, `load_giriton_attendance_from_sheet.py` |
| `foglalasok_raw` | `raw_muszakpro_bookings` | `foglalasok_db.py`, `load_foglalasok_raw.py` |
| `courier_card_stats` | `mart_courier_card_stats` | `courier_card_db.py`, `build_courier_card_stats.py` |
| `discord_route_notifications` | `ops_discord_route_notifications` | `discord_route_monitor.py`, `discord_routes.py` |

## Javasolt atallasi sorrend

1. Raw es stage SQL-ek futtatasa, hogy minden uj tabla meglegyen.
2. Kodbeli tabla-nevek atvezetese uj prefixekre.
3. Robotok kezi tesztje egyesevel:
   - `jitt-invoice-performance`
   - `dsp-live-drivers`
   - `discord-route-monitor`
   - `giriton-attendance`
   - `girition`
   - `dsp`
4. Csak ezutan fusson a tenyleges tabla-atnevezo SQL.

## Megjegyzes

Egyszeru olvaso view nem eleg az atallashoz, mert tobb script `upsert`/`on_conflict`
REST hivasokat hasznal. Ezeket jobb valodi tablaval es frissitett kodnevekkel futtatni.
