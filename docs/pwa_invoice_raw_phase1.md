# PWA Excel-feltöltés – Phase 1

## Hatókör

Csak fájlfeltöltés, RAW mentés és a kiválasztott hónap fájljainak listázása.
Nincs munkalaponkénti külön tábla, üzleti duplikációkezelés, összehasonlítás,
kártyákhoz rendelés, normalizálás, számítás vagy publikálás.

A régi elszámolás adatbázistáblái, importvégpontjai és számítási/publikálási függvényei nem változnak.
Az Elszámolás feltöltés felületének 1–2. lépése az új, önálló feltöltési modult használja.
A 3–4. lépés ebben a fázisban nem indítható. A félretett TESZT kísérletet nem kapcsoljuk be.

## Tárolás

- Új, önálló gyűjtőtábla: `public."PWA_INVOICE_RAW"`. Egy sor = egy teljes feltöltött Excel.
- Egyedi technikai feltöltési UUID és külön olvasható sessionazonosító:
  `JITT_YYYY_MM_123456`, a kiválasztott elszámolási hónappal. A hatjegyű részt
  az adatbázis osztja ki egyediségellenőrzéssel.
- Eredeti fájl privát Storage-ban: `pwa-attachments/pwa-invoice-raw/<uuid>/original.<kiterjesztés>`.
- A `raw_data` JSONB mező minden munkalapot együtt tartalmaz, eredeti névvel és sorrenddel.
  Az üres munkalapnak is van bejegyzése. A nem üres sorok külön UUID-t,
  eredeti Excel-sorszámot és oszlophelyeket kapnak.
- XLSX/XLSM esetén a képletszöveget és a fájlban tárolt eredményt külön megőrizzük;
  képletet nem számolunk újra. XLS esetén a kiolvasható értékek és az eredeti bináris fájl maradnak meg.
- A nyilvántartás tartalmazza a hónapot, fájlnevet, SHA-256 ellenőrzőösszeget,
  méretet, munkalap- és RAW-sorszámot, feltöltőt és időpontot.
- A sor csak az eredeti fájl tárolása és az atomikus RAW DB-mentés után kap `saved` állapotot.
  Hiányzó/hibás beolvasás nem jelenhet meg teljes sikerként.

## Feltöltés és lista

Az első lépésben hónapot választunk. A második lépésben több Excel választható egyszerre,
vagy további fájlok adhatók hozzá később. A fájlok külön kerülnek mentésre;
nem írják felül egymást. A felület a feltöltés után a 2. lépésben marad.

A lista már a 2. lépés megnyitásakor lekérdezi a hónap meglévő RAW feltöltéseit.
Fájlnév, sessionazonosító, feltöltési idő, munkalapszám, RAW-sorszám és mentési állapot látszik.
A lista lapozható, a RAW tartalmat nem tölti le minden listázáskor.

Fájlonként külön mentési eredmény van. Részleges hálózati hiba esetén csak a nem igazolt
fájl marad újrapróbálásra, ugyanazzal a kérésazonosítóval. Ez a szállítási idempotencia:
nem a később tervezett üzleti összehasonlítás vagy sor-duplikációkezelés.
Ha a felhasználó ugyanazt a fájlt új feltöltésként választja ki, ebben a fázisban külön bejegyzés készül.

## Telepítés

1. Supabase SQL Editorban futtatandó: `sql/pwa_invoice_raw_phase1.sql`.
   Csak az új táblát, annak indexét és a hozzá tartozó mentési RPC-t hozza létre.
   A migráció újrafuttatható.
2. A meglévő `pwa-attachments` bucket maradjon privát. A jelenlegi octet-stream típus és
   10 MB fájlkorlát használható; nincs szükség publikus URL-re vagy új bucketre.
3. Függőségek telepítése a requirements.txt alapján, az XLS olvasásához `xlrd` is szükséges.
4. A PWA API és a v260 kliens együtt telepítendő. Új kliensmodul: `pwa/invoice_raw.js`.

Az alkalmazás szolgáltatáskulcsával nem futtatható táblalétrehozás. Ha a SQL még nem futott,
a feltöltés/listázás ezt 503-as, konkrét hibaüzenettel jelzi; nem tér át az éles importtáblára.
A fejlesztés során a migráció külön PostgreSQL tesztkörnyezetben lett ellenőrizve;
az éles táblalétrehozás nem történt meg.

## Új végpontok

- `GET /api/admin/pwa-invoice/raw?month=YYYY-MM&offset=0&limit=50`
- `POST /api/admin/pwa-invoice/raw/excel` — multipart: `month`, `request_id`, `excel_file`

Mindkettőhöz a meglévő elszámolási adminjog kell. A táblát és RPC-t anon/authenticated
szerepkör közvetlenül nem olvashatja/hívhatja. Csak a szerver szolgáltatási hozzáférése használja.

## Ellenőrzések

- `tests/test_invoice_raw_phase1.py`: RAW beolvasás, üres munkalap, eredeti koordináták,
  képlet és tárolt eredmény, típusok/0/false, idempotens újrapróbálás, részleges hibák,
  privát tárhely és jogosultság.
- `tests/test_invoice_raw_sql.cjs`: tényleges PostgreSQL migráció és mentési RPC külön
  PGlite környezetben, session-egyediség, eredeti RAW megőrzése, havi szűrés, hozzáférés.
- `tests/test_invoice_raw_ui.cjs`: négy fájl, egy fájl hibája/újrapróbálása, listafrissítés,
  hónapváltás, mobilos megjelenés és a régi számítási végpontok kizárása.
