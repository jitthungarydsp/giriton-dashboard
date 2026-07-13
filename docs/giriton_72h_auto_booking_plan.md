# Giriton automatikus muszakfoglalas Foglalasok alapjan

Cel: a regi Foglalasok tablaban szereplo T+3 napi vagy azon tuli muszakigenyeket
automatikusan megtalalni a Giriton Shift subscription feluleten, majd kesobb elesen
feliratkoztatni a megfelelo futart.

## Forras

A forras a Foglalasok tabla:

- Google Sheetbol jon
- a sajat rendszerben DB-be is atkerul
- tablajeloltek:
  - `raw_muszakpro_bookings`
  - `foglalasok_raw`

Fontos: a Foglalasok tabla forrasadat, nem irjuk felul.

## Folyamat

1. Robot belep a Giritonba.
2. Megnyitja a Shift subscription oldalt.
3. Kivalasztja az osszes raktarat.
4. Beolvassa a Foglalasok tablaban levo T+3 napi foglalasokat.
5. Ezekbol listat epit:
   - datum
   - raktar
   - muszak kezdete
   - futar neve
   - futar e-mail
   - futar ID
   - foglalasi kod
6. Veszi a lista elso elemet.
7. Beallitja a Giriton datummezot az adott napra.
8. Megnezi, melyik raktarhoz tartozik.
9. Megnezi, milyen muszakot kert az ember.
10. Megkeresi a Giriton feluleten a megfelelo muszakkartyat.
11. Rakattint.
12. Hozzaadja a futart.
13. Ellenorzi az eredmenyt.
14. Log tablaba irja a probalkozast.
15. Jon a lista kovetkezo eleme.

## Mostani implementalt allapot

Fajlok:

- `resources/giriton_auto_booking.py`
- `giriton_auto_booking_github.robot`
- `docs/supabase_giriton_auto_booking_log.sql`

A robot jelenleg dry-run modban mukodik:

- beolvassa a Foglalasok T+3 listat
- datumot allit Giritonban
- megkeresi a megfelelo muszakkartyat
- logolja, hogy megtalalta-e
- nem adja hozza elesben a futart

Ez szandekos vedelmi lepes, mert a Giriton hozzaadasi modal pontos DOM-utvonala
meg nincs rogzitve.

## Log tabla

Tabla:

```text
ops_giriton_auto_booking_log
```

Egy sor = egy robot probalkozas.

Fontos statuszok:

- `DRY_RUN_FOUND`
- `SHIFT_CLICKED`
- `SHIFT_NOT_FOUND`
- kesobb: `COURIER_ADDED`
- kesobb: `ALREADY_BOOKED`
- kesobb: `NO_CAPACITY`
- kesobb: `ERROR`

## Elesites elotti kovetkezo pont

Meg kell nezni egy konkret Giriton muszakkartyara kattintas utan:

1. milyen modal nyilik meg
2. hol van a futar hozzaadas gomb
3. hogyan lehet futar nev/e-mail alapjan keresni
4. milyen gomb menti a valtozast
5. milyen szovegbol ellenorizheto, hogy a futar tenyleg felkerult

Amint ez megvan, a dry-run utani reszt lehet elesiteni.
