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

### fetch-drivers tervezett tarolasi logika

Ezt a hivast percenkent szeretnenk futtatni.

Fontos elv:

- a hivas live allapotot ad
- nem minden percben kell minden mezot tortenetileg elmenteni
- az aktualis allapotot mindig frissiteni kell
- historikus sort csak akkor erdemes irni, ha valami lenyeges valtozott

Javasolt adatbazis logika:

1. Aktualis allapot tabla

Pelda tabla:

```text
dsp_driver_live_state
```

Ebben futaronkent csak egy aktualis sor van.

Kulcs:

```text
driver_id
```

Minden percben frissulhet.

Ide kerulhet:

- `driver_id`
- `active`
- nev
- e-mail
- telefonszam
- raktar
- auto tipus
- rendszam
- homerseklet
- utolso homerseklet meres ideje
- aktualis statusz
- keses percben
- kovetkezo cim
- indulas kesesben van-e
- loading_finished_at
- warehouse_departure_real
- aktualis pozicio
- route_assigned_at
- current_shift
- route statistics aktualis ertekei
  - teljes tav km
  - megtett tav km
  - kivitt csomagok
  - osszes csomag
- utolso frissites ideje

2. Valtozasnaplo tabla

Pelda tabla:

```text
dsp_driver_live_events
```

Ide csak akkor irunk uj sort, ha valami lenyeges valtozik.

Pelda valtozasok:

- `active` valtozik
- `status.current_state` valtozik
- rendszam valtozik
- homerseklet riasztasi szintet lep at
- `route_assigned_at` valtozik
- `next_stop` valtozik
- `parcels_delivered` valtozik
- `is_departure_delayed` valtozik
- uj route / uj route statistics jelenik meg

3. Percenkenti nyers snapshot csak rovid ideig

Ha kell debug vagy live visszanezes, lehet kulon rovid eletu snapshot tabla.

Pelda:

```text
dsp_driver_live_snapshot
```

Ebben percenkenti allapot lehet, de csak rovid ideig, peldaul 7-14 napig.

Ez nem elszamolasi fo adat, inkabb diagnosztikai / live kovetesi adat.

### Terheles becsles

Ha percenkent hivjuk:

```text
60 hivas / ora
1440 hivas / nap
```

Ha egy hivasban kb. 30-60 futar van, es minden futarrol minden percben irnank sort:

```text
kb. 43 000 - 86 000 sor / nap
```

Ez adatbazisnak meg kezelheto, de felesleges es gyorsan nagyra no.

Jobb megoldas:

- `dsp_driver_live_state`: mindig csak futaronkent 1 aktualis sor
- `dsp_driver_live_events`: csak valtozas esemenyek
- opcionlis `dsp_driver_live_snapshot`: rovid ideig megtartott percenkenti debug adat

Igy a rendszer gyors marad, es nem tarolunk felesleges duplikalt adatot.

### Nyitott kerdesek ehhez a hivashoz

- Kell-e minden percrol nyers snapshot, vagy eleg az aktualis allapot + valtozasnaplo?
- Mennyi ideig tartsuk meg a percenkenti debug snapshotot?
- Pontosan mely statusz valtozasok legyenek esemenykent mentve?
- A `route.timing` mezok az aktualis cimre vagy a teljes route-ra vonatkoznak?
- A `statistics` valtozasnal eleg-e csak a kulonbseget naplozni, vagy kell teljes allapot is?

### Route / kilometer adatok

A kilometer adatok fontosak, ezeket kulon figyelni kell.

Forras:

- `route.statistics.total_distance_km`
- `route.statistics.distance_covered_km`

Tarolasi elv:

- az aktualis allapot tablaban mindig latszodhat a jelenlegi `total_distance_km` es `distance_covered_km`
- kulon kilometer valtozasnaplo nem kell
- a route adatot kulon route osszesito tablaba kell menteni
- menteni akkor kell, amikor a route vege latszik
- route vege jelzes: `status.next_stop` vagy `next_stop` erteke `null`

Tervezett tabla:

```text
dsp_route_summary
```

Elsodleges kulcs:

```text
driver_id
```

Masodlagos / kapcsolo kulcs:

```text
loading_finished_at
```

Indok:

- ebben a live hivasban nincs kulon route ID
- az elsodleges azonosito ezert a `driver_id`
- a `loading_finished_at` segit beazonositani es osszekotni mas tablakkal, hogy pontosan melyik tura volt
- egy futarnak egy napon tobb turaja is lehet, ezert a `driver_id` onmagaban nem eleg a konkret tura elvalasztasara
- a tura szintu egyediseghez a `driver_id + loading_finished_at` paros hasznalhato

Tervezett mezok:

- `driver_id`
- `courier_name`
- `warehouse_name`
- `license_plate`
- `loading_finished_at`
- `warehouse_departure_real`
- `route_assigned_at`
- `total_distance_km`
- `distance_covered_km`
- `parcels_delivered`
- `parcels_total`
- `finished_at`
- `source_updated_at`

Nullazodas:

- A route `statistics` akkor nullazodik, amikor a futar uj turat kap.
- Mivel nincs route ID ebben a live hivasban, az uj tura felismeresenel a `loading_finished_at`, `route_assigned_at`, `warehouse_departure_real` es a statistics valtozasa lesz fontos.

Leendo felhasznalas:

- napi futar kilometer
- havi futar kilometer
- auto hasznalat / terheles
- route hatekonysag
- becsult uzemanyag / futasi koltseg
- statisztikai KPI

Nyitott kerdes:

- Biztosan eleg-e a `next_stop = null` a route lezart allapot felismeresehez?
- Pontosan melyik idoertek a legstabilabb egy tura azonositashoz: `loading_finished_at`, `route_assigned_at` vagy `warehouse_departure_real`?
- Ha `loading_finished_at` ures, milyen potazonositot hasznaljunk?

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
