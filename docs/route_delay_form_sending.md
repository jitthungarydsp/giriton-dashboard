# Reklamációk elküldése – devtest

Az admin és pénzügyi szerepkörök oldalsó menüjében külön oldal kezeli az Excelből származó reklamációtervezeteket.

1. Töltsd fel a kategóriajavaslatos Excelt (`Reklamációs túrák`) vagy a módosítható űrlaplistát (`Űrlapok`).
2. Importálás előtt választható, hogy a korábbi, még be nem küldött tervezetek felülírhatók-e. Alapesetben megmaradnak a korábbi szerkesztések.
3. Szűrj hónapra, futárra, túrára vagy státuszra; válaszd ki a kezelendő tételt.
4. Szerkeszd és mentsd az adatokat. A Google-űrlap linkje mindig az elmentett sorból készül, helyi indítóprogram nélkül.
   A partnernek szánt leírás rövid, „Tisztelt Megbízó!” megszólítású levél, a futár nevével, túraszámával, kategóriájával és az opcionális végleges indoklással. A belső forrásadatok és ellenőrzési figyelmeztetések a kezelőfelületen maradnak.
5. Az előnézet nem jelent ellenőrzést vagy beküldést. Az „Adatok ellenőrizve” csak végleges indoklás és szükséges egyeztetések után válik elérhetővé.
6. A Google-űrlapon kézzel történik a beküldés. Kizárólag annak visszaigazolása után rögzítsd a beküldést, bizonyítékhivatkozással vagy azonosítható megjegyzéssel.

A letöltött JSON-munkapéldány ugyanott visszatölthető. Megőrzi az ellenőrzött és visszaigazolt státuszokat; módosított vagy hibás tartalmú mentést nem állít vissza ellenőrzöttként.

A beküldött sor zárolt. A tervezet módosítása megszünteti a korábbi ellenőrzött állapotot. Egy ismételten feltöltött futár/nap/túra nem hoz létre második példányt.

## Tartós tárolás

Futtasd a `sql/route_delay_form_drafts.sql` migrációt a meglévő settlement adatbázison. Az új tábla független az elszámolásoktól és a PWA reklamációitól. RLS mellett kizárólag a szerver service-role kapcsolata kap hozzáférést.

Tárolási hiba esetén a felület munkameneten belüli előkészítésre használható; ezt jelzi, és munkapéldány letöltését kínálja. Az adatbázisban végzett módosítások verzióellenőrzéssel mentődnek: másik admin közben végzett szerkesztése vagy beküldésrögzítése nem írható felül.

Ellenőrzés: `python -m unittest tests.test_route_delay_draft_management tests.test_route_delay_excel_forms tests.test_quality_form_forwarding`.
