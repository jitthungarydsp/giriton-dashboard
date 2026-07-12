# DSP route story logika

Cel: minden route ID kapjon egy rovid, emberileg olvashato tortenetet 2026-06-01-tol visszamenoleg.

## Forrasok

- Elsodleges stage forras:
  - `dsp_shift_route_summary`: route + muszak parositas.
  - `dsp_order_arrivals`: cimszintu tervezett/valos erkezes es idoablak statusz.
- Raw fallback:
  - `dsp_attendance_raw`: `fetch-attendance` napi JSON, ebbol jonnek a muszakok, `availableForShiftSince` es route idok.
- `dsp_driver_detail_raw`: `fetch-drivers-detail` napi/futar JSON, ebbol jonnek a cimek es idoablakok.
- `dsp_route_distance_calculated`: route ID szintu szamolt GPS tavolsag.
- `foglalasok_raw`: MuszakPro/Foglalasok sorok, ebbol jon a napi foglalt muszakszam es a kovetkezo muszak kockazata.
- Cel tabla: `mart_dsp_route_stories`.

## Fo mezok

- Sorba allas: `available_for_shift_since`.
  - Ha ez nincs, de van `courier_registered_at`, akkor a varakozas szamitasahoz `courier_registered_at` a fallback kezdopont.
- Muszak kezdete: `shift_start`.
- Tura kiosztasa: `assigned_at`.
- Tura letrehozasa: `route_created_at`.
- Tervezett bepakolas vege: `loading_time`.
- Valos indulas: `real_departure`.
- Tervezett indulas: `planned_departure`.
- Tervezett visszaerkezes: `planned_return`.
- Valos visszaerkezes: `real_return`.
- Megtett tavolsag: `gps_distance_km`, fallback informaciokent `checkpoint_straight_km`.
- Foglalas szerinti muszakok: `foglalasok_raw` sorok szama `(work_date, courier_id)` szerint.

## Szamitasok

- Sorba allasi elteres: `available_for_shift_since - shift_start`.
  - Fallback: `courier_registered_at - shift_start`.
  - Pozitiv: kesve jelentkezett elerhetonek.
  - Negativ: elobb jelentkezett elerhetonek.
- Varakozas turara: `assigned_at - available_for_shift_since`.
  - Fallback: `assigned_at - courier_registered_at`.
- Tervezett bepakolasi ido: `loading_time - assigned_at`, ha van `loading_time`.
  - Fallback: `planned_departure - assigned_at`.
- Valos bepakolasi ido: `real_departure - assigned_at`.
- Tervezett turaido: `planned_return - planned_departure`.
- Valos turaido: `real_return - real_departure`.
- Teljes kiosztastol visszaerkezesig ido: `real_return - assigned_at`.
- Kovetkezo muszak kesesi kockazat:
  - megkeresi az adott futar kovetkezo foglalt muszakjat ugyanazon a napon,
  - ha `real_return` kesobb van, mint a kovetkezo muszak kezdete, akkor keses,
  - ha korabban van, akkor a kulonbseg a tartalek ido.
- Tervezett cimhez kepest korai/keso: `tervhez_kepest_perc`.
- Idoablakhoz kepest korai/keso: `idoablakhoz_kepest_statusz`, illetve ahol lehet, `valos_erkezes` es `idoablak_kezdete`.

## Manuialis kiosztas

Ha nincs `available_for_shift_since`, de van `assigned_at`, akkor a story szoveg ezt irja:

`Nem latszik sorba allas, de turat kapott, ezert manualisan raktak ra.`

Ha nincs `courier_registered_at`, de van `assigned_at`, akkor ezt manualis kiosztasnak jeloljuk:

`DSP route regisztracio ideje: nincs adat, ez manualis tura kiosztast jelez.`

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

A raw JSON forrasokat napi bontasban olvassa, mert a `response_json` mezo nagy,
es egy teljes honap egyben Supabase statement timeoutot okozhat.

Proba feltoltes nelkul:

```powershell
python scripts\build_dsp_route_stories.py --start-date 2026-06-01 --end-date 2026-06-01 --raw --dry-run
```
