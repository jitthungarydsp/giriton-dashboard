# Félretett PWA pénzügyi munkafolyamat

A fejlesztés nincs aktív használatban. Éles adatbázis-módosítás és deploy nem történt.

## Tartalom

- Tételes PWA-s szerkesztés a Kiflis levonások/bónuszok, JITT bónusz/malus és Korrekciók csoportban.
- Közös PWA/devtest snapshot és import utáni kézi módosításmegőrzés.
- Tranzakciós importmentés, SQL-migráció, dokumentáció és tesztek.
- Tesztelt állapot: 72 Python-teszt, 11 PostgreSQL-ellenőrzés és helyi böngészőteszt sikeres.

A később kért egyfutáros szűkítés még NINCS beépítve. Visszavétel előtt ezt kell
elkészíteni: Gurzó Balázs, #7644, 2026-10. Más futár/hónap maradjon a régi ágon.

## Visszavétel

A repó gyökerében először ellenőrizd:

    git apply --check docs/parked-finance-workflow-20261110/feature.patch

Ha tisztán alkalmazható és újra dolgozunk a feladaton:

    git apply docs/parked-finance-workflow-20261110/feature.patch

Ez helyreállítja a fejlesztést és a hozzá tartozó új fájlokat. Ha ütközést jelez,
ne erőltesd: a patch alapján kézzel kell átvezetni a közben megváltozott részeket.
Az archívumot tartalmazó mentési commitot ne cherry-pickeld megvalósításként:
az a mentési csomagot tartalmazza, nem aktiválja a fejlesztést.

## Élesítés előtt

1. Az egyfutáros/hónapos korlátozás beépítése és tesztelése.
2. Az archivált dokumentáció és SQL-migráció felülvizsgálata.
3. Összehangolt átállás; régi importfutás nem maradhat átfedésben.
4. Ellenőrzött próba kizárólag #7644 / 2026-10 adataival.

A tömeges státuszkezelés, az Excel-felismerési/büntetésjavítások és az egyéb
már folyamatban lévő változtatások nem részei ennek a félretételnek.
