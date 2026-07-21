# JITT elszámolás PWA indítás

## 1. DB struktúrák

Supabase SQL Editorban futtasd:

```sql
-- docs/settlement_schema.sql
```

Ez létrehozza többek között:

- `public.settlement_courier_master`
- `public.settlement_api_calls`
- `public.settlement_financial_overview_raw`
- `settlement.courier_master` view
- `settlement.api_calls` view
- `settlement.financial_overview_raw` view

## 2. Futár törzs frissítés

Először próbaként:

```powershell
cd C:\Giriton\giriton-dashboard
python scripts\load_settlement_courier_master.py --dry-run
```

Éles DB írás:

```powershell
cd C:\Giriton\giriton-dashboard
python scripts\load_settlement_courier_master.py
```

A script:

- meghívja a `fetch-drivers` API-t,
- ha eléri, beemeli a meglévő `courier_master` törzset,
- frissíti a `settlement_courier_master` táblát,
- naplózza a hívást a `settlement_api_calls` táblába.

## 3. Courier Hub financial overview

Az elszámolás menü első körben ezt a Courier Hub hívást kéri le:

```text
/services/courier-hub-service/external/warehouses/{warehouse_id}/dsps/8/financial-overview/courier-overview?year={year}&month={month}
```

A token nem kerül a böngészőbe és nem kerül kódba. A backend ezt olvassa:

```powershell
$env:COURIER_HUB_ACCESS_TOKEN="ide_jon_az_aktualis_token"
```

Ha a Courier Hub `/api/auth/session` teljes JSON válasza van kéznél, akkor alternatívaként ez is használható:

```powershell
$env:COURIER_HUB_SESSION_JSON='{"accessToken":"..."}'
```

Ha cookie alapján akarjuk lekérni a session tokent, akkor ezt is tudja:

```powershell
$env:COURIER_HUB_SESSION_COOKIE="a_courier_hub_cookie"
```

A régi importer beállításnevei is működnek:

```text
KIFLI_COURIER_HUB_AUTHORIZATION
KIFLI_COURIER_HUB_BEARER_TOKEN
KIFLI_COURIER_HUB_COOKIE
KIFLI_COURIER_HUB_API_KEY
KIFLI_COURIER_HUB_EXTRA_HEADERS_JSON
```

Streamlit/hosting secretként ezek közül legalább az egyik kell:

```text
COURIER_HUB_ACCESS_TOKEN
COURIER_HUB_SESSION_JSON
COURIER_HUB_SESSION_COOKIE
```

A token kb. 24 óra után lejár, ezért most kézzel frissíthető. A későbbi stabil megoldás egy külön token-frissítő folyamat lesz.

A lekérés raw mentése ide történik:

```text
public.settlement_financial_overview_raw
```

## 4. App indítás lokálisan

```powershell
cd C:\Giriton\giriton-dashboard
python elszamolas_api.py
```

Megnyitás:

```text
http://127.0.0.1:8530/
```

Az új `Főoldal` menü a `settlement_courier_master` táblával dolgozik. Az `Elszámolás` menüben van a Courier Hub financial overview lekérés és raw mentés.
