# Automatikus futárjóváhagyás és jelszó-visszaállítás

A feldolgozó önálló folyamat, amelyet GitHub Actions ütemezetten futtat. Nem kell hozzá nyitva lennie a devtestnek, nem ír users.json fájlt, és nem módosít elszámolást.

## Működés

- Új PWA-regisztráció és visszaállítási kérelem kis adatbázis-várólistára kerül.
- A worker kizárólag a már nyilvántartott, aktív futártörzshöz illeszkedő adatokat engedi tovább. Regisztrációnál az azonosító, a név és a törzs e-mail-címe egyezzen; visszaállításnál a meglévő aktív mobilfiók e-mail-címének is egyeznie kell. Az adminisztrátori és egyéb kiemelt DB-fiókok automatikus kezelése tiltott.
- Nincs e-mail-cím beírása a törzsbe egy nyilvános visszaállítási kérésből. Hiányzó, eltérő adatoknál adminellenőrzés kell.
- A levél egy 30 percig érvényes, egyszer használható jelszóbeállító linket tartalmaz. A DB-ben csak a token SHA-256 lenyomata van. A token az URL fragment részében érkezik, nem GET-paraméterben, és az oldal rögtön eltávolítja a címsorból.
- A meglévő jelszó a sikeres beállításig változatlan. Új regisztrációnál a mobilfiók csak a link felhasználásakor jön létre. A futártörzs adatait a robot nem írja át.
- A link felhasználása tranzakcióban történik. A lejárt, felhasznált, visszavont kérelemhez tartozó vagy közben megváltozott fiókhoz kiadott link elutasításra kerül. A párhuzamos linkfelhasználások futáronként zároltak.
- Az új DB-jelszót a régi JSON-jelszó nem kerülheti meg. A jelszóváltozás előtt kiadott PWA-munkamenetek érvénytelenné válnak. DB-kiesésnél a belépés és a session-ellenőrzés nem esik vissza régi JSON-hitelesítésre.

## Állapotok

`queued` → `processing` → `sending` → `sent`.

- `manual`: az adategyezés nem igazolt vagy 30 percen belül már történt küldés ehhez a futárhoz.
- `failed`: megkezdett levélküldés előtti elakadás, admin újra sorba teheti.
- `uncertain`: a küldés elkezdődött, de a sikere nem igazolt. Nincs automatikus ismétlés, és nincs jelszócsere. A link a lejáratáig működhet, ha a levél mégis megérkezett.

Ugyanaz a kérelem csak egyszer szerepel a várólistán. Az újabb kérelmek sem eredményeznek 30 percen belül újabb automatikus levelet. A DB-jobs tábla a részletes állapotot, az eredeti kérelmek megjegyzése a feldolgozás eredményét mutatja. A devtest jóváhagyó gombjai bekapcsolt automatizálásnál ugyanebbe a sorba tesznek, nem generálnak azonnal jelszót. A törzsadatok rendezése után a `manual`/`failed` munkát az admin újra ellenőriztetheti. A `sent`/`uncertain` munka nem ismételhető így.

## Telepítés

### GitHub Actions – PWA SMTP és Render háttérfolyamat nélkül

A `.github/workflows/pwa-account-automation.yml` az önálló feldolgozót futtatja, ötperces cron ütemezéssel és kézi indítással. Az ütemezés késhet. Nem szükséges Render Background Worker, és a PWA-nál nem kell SMTP-beállítás.

1. Előbb alkalmazd az alábbi SQL-migrációt, majd telepítsd a jelszóbeállító PWA-t. A PWA és a devtest környezetében legyen `PWA_ACCOUNT_AUTOMATION_ENABLED=true`.
2. GitHub → Settings → Secrets and variables → Actions → Secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SMTP_USERNAME` (system@jitt.hu), `SMTP_PASSWORD` (a jelenlegi Google-alkalmazásjelszó). Ezeket ne írd a YAML-ba vagy a repóba.
3. Ugyanitt Variables: `PWA_PUBLIC_URL=https://futar.jitt.hu`. A `PWA_ACCOUNT_AUTOMATION_ENABLED=true` változót csak a migráció és a PWA telepítése után add meg. Addig a job kihagyott állapotú.
4. Actions → PWA_ACCOUNT_AUTOMATION → Run workflow. A korábbi nyitott kérelmek felvételét csak akkor jelöld be, ha azokat is fel kell dolgozni; alapértelmezésben az új kérelmek mennek.
5. Az első éles levélküldés eredményét a job kimenetében és a kérelem adminmegjegyzésében ellenőrizd. Sikeres küldés után a kapott linkkel tesztelhető a jelszóbeállítás.

A GitHub Actions futások a repóhoz tartozó Actions-keretet fogyasztják; nem állítjuk, hogy a futtatás korlátlanul ingyenes. A job nem készít adatokat vagy levelezési titkokat tartalmazó artifactot, és nem commitol.

### Alternatíva: saját worker vagy cron

1. Supabase SQL Editor: `sql/pwa_account_automation.sql`, a meglévő `docs/pwa_users.sql`, regisztrációs és visszaállítási táblák után. A migráció nem küld levelet, nem dolgozza fel a régi kérelmeket, és nem változtat jelszót.
2. Telepítsd a PWA API-t és a felületet. A jelszóbeállító oldal a PWA része (`account_setup.js`).
3. A PWA, devtest és a worker környezetében: `PWA_ACCOUNT_AUTOMATION_ENABLED=true`. Alapértelmezésben kikapcsolt.
4. A worker környezetében: `PWA_PUBLIC_URL=https://futar.jitt.hu`, a meglévő `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` és működő levélküldési beállítások. A publikus URL a tényleges, telepített PWA-ra mutasson, útvonal nélkül.
5. Render Background Worker indítási parancs: `python scripts/run_pwa_account_worker.py --watch`. A függőségek a repó meglévő requirements fájljából telepíthetők. 15 másodpercenként legfeljebb 10 munka; nincs teljes futártörzs-szinkron.
6. Alternatíva: percenkénti cron, `python scripts/run_pwa_account_worker.py --once`. Egy futás legfeljebb 10 munkát dolgoz fel. Várólista-foglalás miatt két worker sem küldi ki ugyanazt a munkát.
7. Korábbi nyitott kérelmek egyszeri felvételéhez: `--once --enqueue-existing`. Ezt csak akkor indítsd, amikor az adatok ellenőrzése és a tényleges levelek kiküldése kívánatos. Legfeljebb 100 korábbi kérés kerül be típusonként, változatlanul szigorú ellenőrzéssel.

Az automatizálás a hibás SMTP-hozzáférést nem javítja meg: a levélküldő szolgáltatásnak működnie kell. A jobokban és a worker kimenetében nem szerepel nyers token vagy jelszó. A production SQL-t és a valódi levélküldést a helyi ellenőrzések nem helyettesítik.

## Ellenőrzés

`python -m unittest discover -s tests -p test_account_automation.py`

Az SQL tranzakciókat elkülönített PostgreSQL/PGlite adatbázissal ellenőrzi a `tests/test_account_database.mjs` teszt. A csomag tesztfüggőség, nem éles függőség. `PGLITE_MODULE` változóban megadható a telepített `@electric-sql/pglite` modul abszolút fájlútvonala.
