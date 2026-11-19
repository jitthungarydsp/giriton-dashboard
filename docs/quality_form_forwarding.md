# Jóváhagyott reklamációk Google-űrlapjának kitöltése

A robot kizárólag kitölt. A végső **Küldés** gombot mindig az admin nyomja meg. A kitöltés nem állítja Továbbított státuszra a reklamációt.

## Használat

1. A PWA Futárreklamációk oldalán az admin a **Továbbítás** ablakban ellenőrzi a kategóriát, a szükséges mezőket és az elküldendő szöveget. A bekapcsolt robotnak az **Automatikus kitöltés** gombbal adja át a szerkesztett adatokat. A **Kézi megnyitás** a saját böngészőben nyitja meg az előkitöltött űrlapot.
2. A robot gépén külön Chrome-ablak nyílik, a konfigurált Google-fiókkal. A robot szükség esetén a jelenlegi piszkozatot folytatja, bejelöli az e-mail rögzítését, majd a partner és a kategória kiválasztása után a részletekhez lép, és kitölti azokat.
3. A robot nyitva hagyja az űrlapot. Az admin ellenőrzi az adatokat, kézzel megnyomja a Küldés gombot, és megvárja a Google visszaigazolását. A képek a PWA privát tárhelyén maradnak: a Google-form jelenlegi mezői között nincs képfeltöltés.
4. Csak igazolt beküldés után a PWA **Beküldtem a Google-űrlapot** gombjával rögzíti a továbbítást. Ha ismert, megadhatja a Kifli ügyazonosítót. A robot akkor folytatja a következő üggyel, ha az admin bezárta a robot Chrome-ablakát.

A PWA gombja nem a telefonon nyitja meg a kitöltött űrlapot: az a robotot futtató gépen jelenik meg. A böngészőablak bezárásáig a következő ügy nem indul el.

## Telepítés

1. Futtasd a `sql/pwa_quality_complaint_forwarding.sql` migrációt az eddigi reklamációs migrációk után. A fájl a korábbi draft állapotellenőrzését is frissíti; meglévő reklamációt és elszámolást nem számol újra.
2. A robot gépén Python 3.11+, Chrome és `pip install selenium` szükséges.
3. Környezeti változók: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `QUALITY_FORM_GOOGLE_ACCOUNT=system@jitt.hu`. Helyileg a gyökér `.streamlit/secrets.toml` értékeit is olvassa. Kulcs ne kerüljön parancssorba vagy Gitbe.
4. `python scripts/run_quality_form_worker.py --login`: kézi Google-bejelentkezés a külön profilban. Ezután zárd be a robot összes Chrome-ablakát.
5. `python scripts/run_quality_form_worker.py --check`: bejelentkezési ellenőrzés, beküldés nélkül.
6. `python scripts/run_quality_form_worker.py --watch`: felügyelt, látható kitöltőrobot. A gépnek futnia kell; az ablakok használatához interaktív asztali munkamenet szükséges. `--once` egy jóváhagyott ügyet vesz fel.
7. A PWA környezetében csak sikeres migráció és bejelentkezési ellenőrzés után legyen `QUALITY_FORM_FORWARDING_ENABLED=true`, majd telepítsd a PWA-t.

A profil alapértelmezett helye Windows alatt `%LOCALAPPDATA%/Jitt/GoogleFormRobot`. A `QUALITY_FORM_PROFILE_DIR` felülírja. A profil nem kerülhet a repóba. A Google ismételt belépést vagy kétlépcsős azonosítást kérhet; ezt kézzel kell elvégezni.

## Állapotok és ismétlés

- `queued`: jóváhagyva, kitöltésre vár.
- `processing`: a robot dolgozik. A művelet megkezdését adatbázisban naplózzuk, mielőtt megnyílik a form.
- `prepared`: kitöltve, kézi ellenőrzésre és beküldésre vár. Nem kerül újra a sorba, és nem jelent továbbítást.
- `login_required`: új bejelentkezés szükséges; utána újra jóváhagyható.
- `failed`: a form megnyitása előtti hiba; újra jóváhagyható.
- `uncertain`: a kitöltés/munkamenet megszakadt, vagy eredményének mentése nem igazolható. Ellenőrizd a robot ablakát és az esetleges kézi beküldést. Automatikus újranyitás nincs.
- `sent`: kizárólag az admin igazolt továbbításrögzítése után.

Lejárt munkafoglalásnál a már megkezdett munka nem indul újra automatikusan, így a nyitva hagyott form mellett nem keletkezik második példány.

## Ellenőrzés beküldés nélkül

`python -m unittest discover -s tests -p test_quality_form_forwarding.py`

`--dry-run payload.json`: a `build_payload` által készített helyi JSON kitöltése látható böngészőben, adatbázismódosítás és automatikus beküldés nélkül. Enterre bezárja a robot ablakát. Éles formon ne küldj be kitalált tesztpanaszt.
