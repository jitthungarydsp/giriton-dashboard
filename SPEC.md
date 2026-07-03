# JIT Kifli modul specifikacio

## Cel

Ez a rendszer a JIT egyik modulja lesz, azon belul a Kifli modul.

A cel az, hogy a MuszakPRO, valamint a Kifli sajat rendszereibol erkezo adatok - Giriton es DSP - egy helyen legyenek tarolva, osszekapcsolva es visszakereshetoen kezelve.

Az adatok egy kozos adattarhazba kerulnek, majd ezekre epulnek modulárisan a Streamlit oldalak.

Az elso fazis celja nem az oldalak tovabbepitese, hanem az adattarhaz megtervezese es felepitese.

A vegso cel egy gyors, stabil es megbizhato rendszer, ahol a DSP portal, MuszakPRO, Giriton es kesobb mas operacios forrasok adatai egyseges adatbazisba kerulnek, es ezekre epulnek majd a Streamlit feluletek.

## Hasznalt eszkozok

- Supabase
- Streamlit
- Google Sheet

## Hasznalt nyelvek

- Python
- JavaScript

## Jelenlegi fo adatforrasok

- DSP portal / DSP API-k
- MuszakPro, jelenleg Google Sheetben
- Giriton adatok
- jelenlegi Google Sheetek mint atmeneti adatforrasok es ellenorzo feluletek

## DSP felulet

### fetch-drivers hivas

URL:

```text
https://uftplslamjbbhlozsygo.supabase.co/functions/v1/fetch-drivers?id=JIT&organizationId=f24ea2a1-4ff6-49e0-9f3b-4ef0b6cb3bbc&departureDelayThreshold=10
```

Jelleg:

- aktualis DSP feluleti adatokat jelenit meg
- live/allapot jellegu adatforras
- multbeli adatokat ebbol nem lehet lekerdezni
- a historikus tarolast sajat adatbazisban kell megoldani, ha kesobb vissza akarjuk nezni

Fontos mezok:

- `driver_id`
- `active`
  - fontos mezo
  - azt mutatja, hogy a futar be van-e jelentkezve / aktiv-e
- `personal_info.name`
- `personal_info.contact_email`
- `personal_info.contact_number`
- `personal_info.warehouse_name`
- `vehicle.type`
- `vehicle.license_plate`
- `vehicle.temperature`
- `vehicle.last_measurement_timestamp`
- `status.current_state`
  - ossze kell majd gyujteni, milyen statuszok fordulnak elo
- `status.delay_minutes`
- `status.next_stop`
- `status.is_departure_delayed`
  - `true` / `false`
  - hasznos riasztasi es operacios adat
- `status.loading_finished_at`
- `status.warehouse_departure_real`
- `route.current_position.latitude`
- `route.current_position.longitude`
- `route.path`
- `route.route_assigned_at`
- `route.timing`
  - nyitott kerdes: ezek az aktualis cimre vonatkoznak-e vagy a teljes route-ra
- `route.statistics.total_distance_km`
- `route.statistics.distance_covered_km`
- `route.statistics.parcels_delivered`
- `route.statistics.parcels_total`
- `current_shift.start`
- `current_shift.end`
- `current_shift.shift_type`
- `current_shift.shift_name`

Megjegyzes:

- A `route.statistics` csak akkor nullazodik / valtozik, amikor a futar uj erteket vagy uj route-ot kap.
- Emiatt historikus tarolashoz idobelyegzett snapshotokra lesz szukseg.
- A `fetch-drivers` hivasbol erkezo adatokat kulon live snapshotkent erdemes tarolni, nem elsodleges historikus route forraskent.

## Hosszu tavu irany

- A Google Sheetekbol fokozatosan atvezetjuk az adatokat adatbazisba.
- Az adatbazis lesz az elsoleges adattarhaz.
- A Google Sheet kesobb inkabb ellenorzo, export es kezi munkafelulelet marad.
- A Streamlit feluletek az adatbazisbol dolgoznak majd.

## Elso fazis

Elso korben az adattarhazat tervezzuk meg.

Fontos kerdesek:

- Milyen adatok vannak?
- Honnan jonnek?
- Milyen gyakran frissulnek?
- Milyen kulcsok alapjan kapcsolodnak?
- Mit kell hosszu tavon tarolni?
- Mit eleg ideiglenesen kezelni?
- Mit kell riporthoz es statisztikahoz elokesziteni?

## Kesobbi Streamlit feluletek

### Kiflis kartya oldal

Futar sajat nezete.

Varhato tartalom:

- sajat muszakok
- aktualis route
- teljesitmeny
- bevetelbecsles
- havi statisztikak

### Admin oldal

Rendszerkezeles.

Varhato tartalom:

- felhasznalok
- jogosultsagok
- rendszerbeallitasok

### Koordinator oldal

Napi operacio.

Varhato tartalom:

- mai futarok
- varakozo futarok
- muszak hianyok
- riasztasok
- napi operativ allapot

### Treninges oldal

Futarok fejlesztese es kovetese.

Varhato tartalom:

- treninges futarok
- teljesitmeny kovetes
- oktatasi statisztika
- javitasi pontok

### Statisztika fo oldal

Ceges es futar KPI.

Varhato tartalom:

- napi / heti / havi KPI
- futar statisztika
- route statisztika
- cim statisztika
- kesesek
- varakozas
- expressz / normal bontas

## Alapelv

A tervezest az uzleti logika vezeti.

A technikai feladat az, hogy ezt stabilan, gyorsan es visszakereshetoen kiszolgalja.

## Nyitott kerdesek

- Pontosan mely DSP adatcsoportokat kell hosszu tavon tarolni?
- Mely MuszakPro adatok lesznek kotelezoek?
- Milyen Giriton adatok keruljenek az adattarhazba?
- Mi legyen a kozos elsoleges kulcs a muszakok egyeztetesehez?
- Mennyi honap nyers adat maradjon adatbazisban?
- Mely adatokbol keszuljon elore szamitott snapshot?
