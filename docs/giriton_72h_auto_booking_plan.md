# Giriton 72 oras automatikus muszakfoglalas

Cel: a Giriton feluleten csak olyan muszakot foglaljon a robot, amelynek kezdete
Budapest ido szerint legalabb 72 oraval kesobb van, mint a futas pillanata.

## Jelenlegi allapot

A meglevo Giriton robotok jelenleg olvasnak:

- belepnek a Giritonba
- megnyitjak a Shift subscription oldalt
- datumot allitanak
- vegiggorgetik a muszakokat
- kiolvassak a muszak nevet, raktarat, foglaltsagot es feliratkozott futarokat

Foglalasi/kattintasi logika jelenleg nincs biztonsagosan elvalasztva.

## Javasolt mukodes

1. A foglalasi igeny ne kozvetlenul kattintasbol induljon, hanem egy kulon sorbol.
2. A robot eloszor beolvassa a foglalasi sorokat.
3. Minden sorra ellenorzi:
   - van-e futar azonosito
   - van-e datum
   - van-e raktar
   - van-e muszakkezdes
   - a muszak kezdete `most + 72 ora` utan van-e
   - nincs-e mar lefoglalva ugyanaz a futar ugyanarra a muszakra
   - van-e szabad hely
4. Csak ezutan kattint a Giriton feluleten.
5. Minden eredmenyt naploz:
   - sikeres foglalas
   - kihagyva, mert 72 oran beluli
   - kihagyva, mert nincs szabad hely
   - kihagyva, mert mar foglalt
   - hiba, ha a felulet nem talalhato

## Minimalis foglalasi sor mezok

```text
request_id
courier_id
courier_name
work_date
warehouse
shift_start
requested_by
status
created_at
processed_at
result_message
```

## 72 oras szabaly

```text
shift_start_at_budapest >= now_budapest + 72 hours
```

Ha ez nem igaz, a robot nem foglalhat.

## Hianyzo dontesi pontok

Ezek nelkul nem erdemes eles kattintast bekotni:

1. Honnan jon a foglalasi igeny: DB tabla, Streamlit gomb, vagy Google Sheet?
2. Pontosan melyik Giriton UI gombbal tortenik a feliratkozas?
3. Egy futar neve/e-mailje hogyan valaszthato ki a Giriton modalban?
4. Kell-e raktarszures: BUD1/BUD2/DSP/BUD2 kulon?
5. Kell-e dry-run mod, ahol csak kiirja, mit foglalna?

## Biztonsagi alapelv

Eloszor csak dry-run modban fusson:

```text
Megtalaltam: 2026-07-17 BUD2 15:30 Gurzo Balazs
72 ora szabaly: OK
Szabad hely: OK
Mar foglalt: NEM
Eredmeny: DRY_RUN, kattintas nelkul
```

Eles kattintas csak akkor legyen, ha a dry-run sorok stabilan jo eredmenyt adnak.
