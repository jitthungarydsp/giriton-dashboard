# DSP route story logika

Cel: minden route ID kapjon egy rovid, emberileg olvashato tortenetet 2026-06-01-tol visszamenoleg.

## Forrasok

- Elsodleges stage forras:
  - `dsp_shift_route_summary`: route + muszak parositas.
  - `dsp_order_arrivals`: cimszintu tervezett/valos erkezes es idoablak statusz.
- Raw fallback:
  - `dsp_attendance_raw`: `fetch-attendance` napi JSON, ebbol jonnek a muszakok, `availableForShiftSince` es route idok.
  - `dsp_driver_detail_raw`: `fetch-drivers-detail` napi/futar JSON, ebbol jonnek a cimek es idoablakok.
- Cel tabla: `mart_dsp_route_stories`.

## Fo mezok

- Sorba allas: `available_for_shift_since`.
- Muszak kezdete: `shift_start`.
- Tura kiosztasa: `assigned_at`.
- Valos indulas: `real_departure`.
- Tervezett indulas: `planned_departure`.
- Tervezett visszaerkezes: `planned_return`.
- Valos visszaerkezes: `real_return`.

## Szamitasok

- Sorba allasi elteres: `available_for_shift_since - shift_start`.
  - Pozitiv: kesve jelentkezett elerhetonek.
  - Negativ: elobb jelentkezett elerhetonek.
- Varakozas turara: `assigned_at - available_for_shift_since`.
- Tervezett bepakolasi ido: `planned_departure - assigned_at`.
- Valos bepakolasi ido: `real_departure - assigned_at`.
- Tervezett turaido: `planned_return - planned_departure`.
- Valos turaido: `real_return - real_departure`.
- Teljes kiosztastol visszaerkezesig ido: `real_return - assigned_at`.
- Tervezett cimhez kepest korai/keso: `tervhez_kepest_perc`.
- Idoablakhoz kepest korai/keso: `idoablakhoz_kepest_statusz`, illetve ahol lehet, `valos_erkezes` es `idoablak_kezdete`.

## Manuialis kiosztas

Ha nincs `available_for_shift_since`, de van `assigned_at`, akkor a story szoveg ezt irja:

`Nem latszik sorba allas, de turat kapott, ezert manualisan raktak ra.`

## Frissitesi elv

A feltoltes `upsert` modban fut:

- azonos kulcs: `(work_date, courier_id, route_id)`
- meglevo sort frissit
- uj route sort beszur
- nem torol historikus adatot

## Futtatas

Tabla letrehozasa Supabase SQL Editorban:

```sql
-- docs/dsp_route_story.sql
```

Stage tablakbol:

```powershell
python scripts\build_dsp_route_stories.py --start-date 2026-06-01
```

Kozvetlen raw JSON-bol:

```powershell
python scripts\build_dsp_route_stories.py --start-date 2026-06-01 --raw
```

Proba feltoltes nelkul:

```powershell
python scripts\build_dsp_route_stories.py --start-date 2026-06-01 --end-date 2026-06-01 --raw --dry-run
```
