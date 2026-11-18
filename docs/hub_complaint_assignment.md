# Reklamáció felelőse és e-mailes értesítés

Az adminisztrátori reklamációs ablakban a felelős kiválasztása és a **Felelős mentése és értesítése** gomb menti a kijelölést. Bagoly Zoltán megadott címe `zoltan.bagoly@jitt.hu`. Gurzó Balázs címét a rendszer az aktív, admin jogosultságú `public.pwa_users` rekordból (`courier_id = 7644`) olvassa ki. A böngésző nem adhat meg más értesítési címet.

A mentés admin bejelentkezést és azonos eredetű JSON kérést követel. A futár/hónap/ügyazonosító együtt ellenőrzött. A korábbi kijelölés azonosítója védi a párhuzamos módosításokat; egy művelet ismétlése nem tesz új levelet sorba. A korábbi felelősök és értesítéseik legutóbbi 30 bejegyzése megmarad.

## PWA-profilok és közös megjegyzések

A PWA **Reklamációs feladataim** menüje minden bejelentkezett profil számára elérhető. Alapesetben csak az adott profilhoz rendelt ügyeket mutatja, minden hónapból. Az admin választhatja az **Összes reklamáció** nézetet is. Az elszámolási reklamációk admin kártyáján külön gomb nyitja meg a profilhoz rendelést.

A profilválasztó az aktív `public.pwa_users` rekordokat és a meglévő, aktív régi PWA-profilokat olvassa. Egy letiltott adatbázis-felhasználó nem jelenhet meg újra a régi profilból. Bagoly Zoltán meglévő profilja `#12345`; e-mail-címként a megadott `zoltan.bagoly@jitt.hu` használható, ha a profilban nincs másik cím.

A kijelöléshez írható megjegyzés bekerül az e-mailbe és az ügy közös megjegyzései közé. A későbbi megjegyzéseket az admin és az aktuális felelős is írhatja és láthatja, szerzővel és időponttal. Más profil ezekhez az adatokhoz nem férhet hozzá. Átrendeléskor az előző felelős elveszíti az ügyhöz való személyes hozzáférést. Ezek a közös megjegyzések különböznek a havi belső admin megjegyzéstől és a futárnak küldött reklamációválasztól.

A **Vizsgálat megkezdése** az ügyet `in_progress` állapotba teszi; nem rögzít választ, elfogadást vagy kifizetést. A Hub futárlistáján az ilyen ügy **Reklamáció / Folyamatban** állapotot és külön **Felelős** oszlopot kap. Több nyitott ügy esetén az aktuális felelősök nevei együtt látszanak. A „Reklamáció” szűrő a folyamatban lévőket is tartalmazza; külön a folyamatban lévő állapotra is lehet szűrni.

## Tárolás

Nincs új SQL-migráció. A meglévő `public.peopleforce_card_statuses` tábla egyedi `(courier_id, document_month, action_key)` kulcsa tárolja az ügy belső munkafolyamatát:

- `action_key = internal_complaint_assignment:<reklamáció UUID>`
- `status_note`: verziózott JSON, felelős, kijelölés, előzmények, értesítési állapot.
- `status = open`: feldolgozásra vár vagy folyamatban; `done`: a küldési kísérlet befejeződött. A tényleges eredményt a JSON `notification.status` mezője adja.

Ezek belső ügyintézési rekordok. A PWA `read_workflow_rows` és `status_map` kizárja őket a futárnak visszaadott állapotokból. A Hub is külön kezeli őket; nem állítanak be elfogadást vagy kifizetést, és nem módosítanak pénzügyi snapshotot.

## Levélküldés

A PWA FastAPI élettartamával együtt automatikusan indul a háttérküldő, amely 15 másodpercenként ellenőrzi a tartós sort. A mentés után a Hub háttérben a PWA konfigurált `PWA_API_URL` címének `/api/health` végpontját is meghívja, hogy az esetleg alvó szolgáltatás felébredjen. A Hub statikus oldala mellett a friss PWA-verziót is telepíteni kell; a meglévő Render `autoDeploy` ezt a `main` ágról végzi.

A küldő a meglévő `resources.email_sender` SMTP/Resend beállításait használja. Nincs külön robotablak vagy új e-mail-kulcs a Hubban. A felelős profilját és címét küldéskor is ellenőrzi. A levélben a futár, a hónap, az ügyazonosító, a kijelölő, a bejelentés és a közvetlen ügyhivatkozás szerepel. A Hub-link admin belépést, a PWA-link admin vagy aktuálisan kijelölt profilt igényel.

A küldő feltételes adatbázis-módosítással foglalja le az értesítést. Másik worker vagy egyidejű átrendelés esetén nem küld levelet. SMTP-időtúllépés vagy félbeszakadt küldés után az eredmény **nem igazolt**: nincs automatikus újraküldés. A felületen ilyenkor külön újrapróbálható az értesítés, a kézbesítés ellenőrzése után. Az **Elküldve** állapot a levélküldő szolgáltatás általi átvételt jelenti, nem banki vagy pénzügyi műveletet.

## Ellenőrzések

```text
node tests/test_hub_complaint_assignment.cjs
node tests/test_hub_complaint_ui.cjs
node tests/test_hub_complaint_owners.cjs
node tests/test_pwa_complaint_assignments_ui.cjs
python -m unittest discover -s tests -p test_pwa_complaint_assignments.py
python -m unittest discover -s tests -p test_complaint_assignment_notifications.py
```

A tesztek tesztadatokkal és helyettesített levélküldővel dolgoznak; nem küldenek éles e-mailt.
