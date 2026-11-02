# Phase 2 – RAW kijelölés, összehasonlítás és előszoba

Ez a folyamat a `PWA_INVOICE_RAW` tárolóra épül. Nem használja a régi importáló,
paraméterező, elszámoló vagy publikáló végpontokat; nem készít éles elszámolást.

## Telepítés

A Phase 1 migráció után egyszer futtasd a `sql/pwa_invoice_phase2.sql` fájlt a
Supabase SQL Editorban. Újrafuttatható. Új táblája: `public."PWA_INVOICE_WORK"`.
A RAW táblához egy `deleted_at` mező kerül. A munkapéldányhoz és az író RPC-khez
csak a szerver service-role kapcsolata fér hozzá. A régi elszámolási táblákhoz
nem nyúl. A PWA verziója v264.

## Lépések

1. Hónap választása.
2. Egy vagy több Excel feltöltése, havi lista. Checkbox vagy sorkattintás jelöl;
   a kijelölés zöld, az egyetlen elsődleges forrás külön kiemelt. A kijelölés önmagában
   nem ír adatot. Egy fájl a 3. lépésre vezet, kettő–tíz a 2a összehasonlításra.
3. A 2a nézetben bármely kijelölt fájl lehet az elsődleges. A többi ehhez képest
   mutat munkalap-, sor- és cellaeltéréseket. Visszalépéskor megmaradnak a kijelölések.
4. Tovább: az elsődleges teljes munkafüzet SQL-tranzakcióban átkerül az előszobába.
   Az eredeti RAW tartalom, az összes munkalap (az üresek is), sor- és lapazonosító,
   forrássorszám, cellatípus, képlet és mentett képletérték változatlanul másolódik.
5. A 3. lépés az új munkamenet azonosítójával olvassa az előszobát. Munkalaponként
   lapozható nyers előnézet van. A kártyákra osztás és számítás későbbi feladat.

## Havi kizárólagosság és hibák

A `settlement_month` adatbázis-elsődleges kulcs: havonta legfeljebb egy aktív
munkapéldány létezhet. Minden másolat új UUID-t és `JITT_WORK_…` sessionnevet kap,
és megtartja a forrás RAW feltöltés azonosítóját, sessionnevét és fájl-hashét.
A forrásválasztó RPC szerveroldalon is ellenőrzi a hónapot és a törölt állapotot.

Csere előtt piros megerősítő ablak jelenik meg. Az RPC az előző munkapéldány
azonosítóját is ellenőrzi: egy másik admin vagy lap újabb választása 409-es hibát
ad, nem írjuk felül észrevétlenül. Havi tranzakciós zárolás védi a másolást és a
törlést. Azonos kérés-UUID ismétlése nem készít új példányt. Bizonytalan mentés
után a felület frissen lekéri az aktuális előszobát. A 3. lépés régi UUID-val
nem olvashatja automatikusan az új munkapéldányt.

## Az összehasonlítás jelentése

- A lapok az eredeti nevük alapján felelnek meg egymásnak. Új és hiányzó lap,
  valamint a lapok és egyező sorok sorrendváltozása is látható.
- A teljes sorok tartalmát hasonlítjuk: a véletlen UUID és a sorszám nem tartalom.
  Az ismétlődő sorok darabszáma megmarad; nem végzünk automatikus összefésülést.
- Az egyező sorokat sorrendtől függetlenül párosítjuk, ezért egy beszúrás nem
  változtatja meg látszólag az összes későbbi sort.
- Módosult sorhoz megadható egy vagy több kulcsoszlop (`A` vagy `A,C`).
  A kulcsnak a teljes munkalapon egyedinek kell lennie mindkét fájlban.
  Duplikált kulcs esetén figyelmeztetés és külön hiányzó/új sorok jelennek meg.
- Kulcs nélkül, azonos számú fennmaradó sor esetén a párosítás csak sorrend
  szerinti **javaslat**, piros figyelmeztetéssel. Eltérő darabszám esetén a rendszer
  nem talál ki kapcsolatot: hiányzó/új sorokat mutat.
- Cellánként az elsődleges és a másik fájl értéke, típusa, képlete és mentett
  képletértéke látható. Két numerikus cellánál az eltérés `másik − elsődleges`.
  A képleteket nem értékeljük ki és nem végzünk pénzügyi számítást.
- A sorok részletei 50-es oldalakon töltődnek; a munkapéldány előnézete 30-as
  oldalakon. A kliens nem kapja meg egyszerre az összes RAW tartalmat.

## Törlés

A kijelölt feltöltések megerősítés után eltűnnek a listából és nem választhatók
újra. Ez visszaállítható, logikai törlés: az eredeti fájl és a nyers adatok az
archívumban megmaradnak, amint azt a megerősítő ablak is közli. Az aktív előszoba
forrása nem törölhető; előbb másik forrásra kell váltani. Havi vagy hiányzó
azonosító-eltérés esetén a teljes törlési művelet elutasításra kerül.

## Ellenőrzés

Python: `test_invoice_phase2.py`, valamint a Phase 1 importtesztek.
Playwright: `test_invoice_phase2_ui.cjs`, valamint a Phase 1 feltöltési tesztek.
SQL: `test_invoice_phase2_sql.cjs`, PGlite PostgreSQL futtatókörnyezettel
(`PGLITE_TEST_RUNTIME`). A teszt ellenőrzi a teljes másolatot, havi egyediséget,
újrapróbálást, párhuzamos választás utáni konfliktust, hónapelkülönítést,
törlésvédelmet, megőrzött RAW adatot és anon jogosultságok tiltását.
