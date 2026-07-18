# Courier master Sheet import folyamat

Ez a folyamat arra való, hogy a régi Google Sheet / CSV adatait először egy
ideiglenes táblába mentsük, majd telefon alapján megkeressük hozzá a valódi
`courier_master.courier_id` értéket.

## 1. Staging tábla létrehozása

Supabase SQL Editorban futtasd:

```sql
-- docs/supabase_courier_master_sheet_import.sql
```

Ez létrehozza:

```text
public.courier_master_sheet_import
```

Ide megy fel a Sheet/CSV teljes sora `raw_payload` JSON mezőbe.

## 2. Google Sheet letöltése CSV-be

Google Sheetsben:

```text
File / Download / Comma-separated values (.csv)
```

Mentsd ide:

```text
data/courier_master_import.csv
```

## 3. CSV feltöltése az ideiglenes táblába

Előnézet:

```powershell
python scripts\upload_courier_master_sheet_import.py --csv-file data\courier_master_import.csv
```

Feltöltés:

```powershell
python scripts\upload_courier_master_sheet_import.py --csv-file data\courier_master_import.csv --apply
```

Ha ugyanazt a fájlt újra tisztán szeretnéd feltölteni:

```powershell
python scripts\upload_courier_master_sheet_import.py --csv-file data\courier_master_import.csv --apply --replace-source
```

## 4. Telefon alapján master összekötés

Előnézet:

```powershell
python scripts\promote_courier_master_sheet_import.py
```

Éles frissítés:

```powershell
python scripts\promote_courier_master_sheet_import.py --apply
```

Ha azt is szeretnéd, hogy a megtalált `courier_id` visszaíródjon az ideiglenes
táblába:

```powershell
python scripts\promote_courier_master_sheet_import.py --apply --write-back-id
```

## Fontos szabályok

- A script nem talál ki új `courier_id` értéket.
- Név alapján nem emel át új adatot a masterbe.
- Csak akkor frissít `courier_master` sort, ha a staging telefonszám pontosan
  egy meglévő `courier_master.phone_number` rekordra illeszthető.
- Ha egy telefonszám nincs meg a masterben vagy több emberhez is tartozna,
  akkor a sor kimarad és a riportban látszik.

## Szükséges környezeti változók

```powershell
$env:SUPABASE_URL="https://....supabase.co"
$env:SUPABASE_SERVICE_ROLE_KEY="..."
```
