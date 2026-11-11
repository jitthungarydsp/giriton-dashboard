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

## Egygombos és tömeges beküldés

Az **Összes jelenlegi tervezet és szöveg jóváhagyása** gomb az összes nyitott tervezetet ellenőrzöttre állítja, a jelenlegi tartalomhoz kötött adminisztrátori jóváhagyással. Külön rögzíti a jóváhagyó nevét és időpontját, és nem írja át a futárral egyeztetve mezőt. Az adminisztrátor ezzel a hiányzó egyedi indoklás és forrásellenőrzés mellett is elfogadja a meglévő levélszöveget. Bármilyen tartalmi módosítás törli ezt a jóváhagyást. A beküldött és folyamatban lévő tételeket a gomb nem módosítja.

A frissítéshez a `sql/route_delay_form_auto_submission.sql` migrációt is futtasd a tervezetek alaptáblájának létrehozása után.

A Google-bejelentkezést tartó robot egy futó, Chrome-mal rendelkező gépen dolgozik. A devtest a közös adatbázison keresztül adja át a feladatokat, így a webes felület és a robot külön gépen is lehet. A devtestet kiszolgáló Streamlit Cloud nem irányítja a felhasználó böngészőjét.

1. A robot gépén telepítsd a projekt függőségeit: `pip install -r requirements.txt`.
2. Állítsd be a `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `QUALITY_FORM_GOOGLE_ACCOUNT` értékeket. Helyileg a `.streamlit/secrets.toml` is használható. A Google-fióknak az űrlap beküldésére jogosult fióknak kell lennie.
3. Első alkalommal: `python scripts/run_quality_form_worker.py --login`. Jelentkezz be a külön GoogleFormRobot-profilban, majd zárd be annak Chrome-ablakait.
4. Bejelentkezés ellenőrzése, beküldés nélkül: `python scripts/run_quality_form_worker.py --check`.
5. Beküldőrobot indítása: `python scripts/run_route_delay_submission_worker.py --watch`. Hagyd futni; a külön Chrome-profilt más robot közben ne használja. A korábbi PWA kitöltőrobotot ne futtasd vele párhuzamosan.
6. A devtestben mentsd és ellenőrizd a küldendő tételeket. Az **Összes ellenőrzött reklamáció beküldése** a teljes betöltött lista ellenőrzött tételeit adja át, a keresési szűrőtől függetlenül. A sorba állítás egyetlen adatbázis-tranzakció: elavult sor esetén semmi nem kerül sorba.
7. A robot egymás után kitölti és beküldi az űrlapokat, minden Küldés után megvárja a látható Google-visszaigazolást. A devtest frissíti a státuszokat. A tervezeteket és korábban beküldött sorokat kihagyja.

Egyetlen reklamációhoz a **Beküldés és következő futár** használható. Csak az adott reklamációt küldi be, majd siker után kijelöli a következő nyitott tételt.

Hibánál vagy bizonytalan beküldésnél a robot megáll. Ilyenkor nem indít új automatikus kísérletet. Ellenőrizd a Google-válaszokat vagy visszaigazoló e-mailt. A devtestben rögzíthető a bizonyított siker, vagy külön ellenőrzési megjegyzéssel feloldható a bizonyítottan be nem küldött tétel. Öt percnél régebbi, elakadt feldolgozás ellenőrizendőként jelölhető. A robotot az ellenőrzés után kézzel indítsd újra a még sorban várók folytatásához.

A nyitott feladat tartósan zárolja a sort, így újratöltés, dupla kattintás és munkapéldány-visszatöltés sem küldi be újra automatikusan. A munkapéldány visszatöltése a függő beküldéseket ellenőrizendő állapotba állítja.

Az új beküldő külön program. A meglévő PWA `run_quality_form_worker.py --once/--watch` folyamata továbbra is csak kitölt, automatikusan nem küld be.

Teszt: `python -m unittest tests.test_route_delay_submission tests.test_route_delay_draft_management tests.test_route_delay_excel_forms tests.test_quality_form_forwarding`.
