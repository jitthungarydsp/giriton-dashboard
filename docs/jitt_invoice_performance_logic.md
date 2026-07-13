# JITT Courier Hub performance logika

Ez a dokumentum a Courier Hub performance API-bol jovo uj elszamolasi adatok
ertelmezeset irja le.

Pelda a feluletrol:

| Courier | Shifts | Orders | Delayed | Delay % | Late % | No-show % | Compliance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 7644 | 9 | 97 | 0 | 0.0% | 11.1% | 0.0% | 96.7% |

## 1. Keses mutato

A keses mutato a rendeles/cim alapu kesesi arany.

```text
delay_percent = delayed / orders * 100
```

A peldaban:

```text
0 / 97 * 100 = 0.0%
```

Szerzodeses szintek:

| Szint | Delay % |
| --- | --- |
| Szint 1 | `<= 1.50%` |
| Szint 2 | `1.51% - 3.00%` |
| Szint 3 | `3.01% - 5.00%` |
| Nincs bonusz | `> 5.00%` |

## 2. Turamegfelelesi mutato

A szerzodeses turamegfelelesi mutato rossz aranyt mer, nem jo pontszamot.

```text
compliance_bad_percent = 0.7 * no_show_percent + 0.3 * late_percent
```

A peldaban:

```text
0.7 * 0.0 + 0.3 * 11.1 = 3.33%
```

A feluleten lathato `Compliance` ennek a jo pontszamkent megjelenitett valtozata:

```text
compliance_score_percent = 100 - compliance_bad_percent
```

A peldaban:

```text
100 - 3.33 = 96.67% -> 96.7%
```

Ezert nagyon fontos:

- szerzodeses bonuszhoz: `compliance_bad_percent`
- feluleti megjeleniteshez: `compliance_score_percent`

Szerzodeses szintek:

| Szint | Compliance bad % |
| --- | --- |
| Szint 1 | `<= 2.00%` |
| Szint 2 | `2.01% - 4.00%` |
| Szint 3 | `4.01% - 10.00%` |
| Nincs bonusz | `> 10.00%` |

A peldaban a `3.33%` miatt a turamegfelelesi szint: `Szint 2`.

## 3. Dijosszeg kapcsolasa

A szerzodes kepei alapjan a bonusz osszeg a tervezett turahosszhoz igazodik.
A tablazatokban a 4.5 ora a varosi alap. A tobbi idoaranyos.

Altalanos keplet:

```text
bonus_amount = city_base_amount_for_level * planned_route_hours / 4.5
```

Pelda Szint 1 varosi alapnal:

```text
3000 / 4.5 * 3.0 = 2000
3000 / 4.5 * 5.5 = 3666
```

Ez egyezik a szerzodesben lathato tablaval.

## 4. DB retegek

### Raw

Forras:

- `jitt_invoice_performance_bud1_raw`
- `jitt_invoice_performance_bud2_raw`

Kesobbi prefixelt nev:

- `raw_jitt_invoice_perf_bud1`
- `raw_jitt_invoice_perf_bud2`

Itt az API valasz egyben, JSON-kent van elmentve.

### Stage

Tabla:

- `stg_jitt_invoice_performance_couriers`

Ez mar futar szintu bontott adat:

- `courier_id`
- `shifts`
- `orders`
- `delayed`
- `delay_percent`
- `late_percent`
- `no_show_percent`
- `compliance_bad_percent`
- `compliance_score_percent`
- `delay_level`
- `compliance_level`

## 5. Feldolgozo script

Script:

```text
scripts/build_jitt_invoice_performance_stage.py
```

Feladata:

1. Beolvassa a BUD1/BUD2 raw performance JSON-t.
2. Megkeresi a futar sorokat.
3. Kiszedi a teljesitmeny mezoket.
4. Kiszamolja a hianyzo szazalekokat.
5. Kiszamolja a szerzodeses szinteket.
6. Upserteli a `stg_jitt_invoice_performance_couriers` tablaba.

Fontos: a script rugalmas mezofelismerest hasznal, mert az API pontos JSON-nevei
meg valtozhatnak. Felismeri peldaul ezeket:

- `delay %`, `delayPercent`, `delay_percentage`
- `late %`, `latePercent`, `late_percentage`
- `no-show %`, `noShowPercent`, `no_show_percentage`
- `compliance`, `compliancePercent`

## 6. Kovetkezo ellenorzendo pont

Ha van mar valodi raw JSON a DB-ben, meg kell nezni 2-3 futar sorat:

1. A script ugyanazt hozza-e, mint a Courier Hub felulet.
2. A `compliance_bad_percent` es `compliance_score_percent` nem keveredik-e.
3. A `delay_level` es `compliance_level` a szerzodes szerinti savba esik-e.

## 7. Courier Hub auth frissites

A `scripts/load_jitt_invoice_performance_raw.py` alapbol tovabbra is elfogadja
ezeket a statikus auth beallitasokat:

- `KIFLI_COURIER_HUB_AUTHORIZATION`
- `KIFLI_COURIER_HUB_BEARER_TOKEN`
- `KIFLI_COURIER_HUB_COOKIE`
- `KIFLI_COURIER_HUB_API_KEY`
- `KIFLI_COURIER_HUB_EXTRA_HEADERS_JSON`

Ha a Courier Hub token/cookie lejar es az API `401` vagy `403` valaszt ad,
a script megprobalja lefuttatni ezt a parancsot:

```text
KIFLI_COURIER_HUB_AUTH_REFRESH_COMMAND
```

A parancsnak JSON-t kell kiirnia stdout-ra. Elfogadott formatumok:

```json
{"Authorization": "Bearer ..."}
```

```json
{"bearer_token": "..."}
```

```json
{"headers": {"Authorization": "Bearer ...", "Cookie": "..."}}
```

A script a kapott headerekkel ujrahivja ugyanazt a Courier Hub API kereset.
Ez azert fontos, mert igy a kesobbi login/Playwright vagy refresh-token megoldas
kulon script lehet, az invoice import logikajat nem kell ujra szetszedni.
