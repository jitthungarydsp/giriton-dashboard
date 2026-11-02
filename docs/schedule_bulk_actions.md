# Beosztás: kijelölés, tömeges műveletek, aktív futárszűrés

Az adott napi összesítő kártyák alatt név/ID kereső jelenik meg. A keresés ékezetfüggetlen,
több szóra működik, és a teljes slotkártyákat szűri: csak azok maradnak, amelyekben
legalább egy megfelelő futár szerepel. Üres slotot aktív keresés nem mutat.

A törléshez jelölőnégyzet, a szabad slotnál a kiválasztott futárhoz **Foglalás kijelölése** gomb tartozik.
Ezek nem küldenek Hub-kérést. Több futár és több slot összeállítható ugyanarra a napra/raktárra.
A kijelölések szűrés, részletfrissítés és napváltás közben megmaradnak az adott oldal munkamenetében.
Az oldal újratöltése az el nem indított kijelöléseket nem őrzi meg.

Az aktív keresésnél a csoportos kijelölés csak a keresésnek megfelelő futárok foglalásait jelöli;
ugyanabban a slotban szereplő másik futárt nem jelöl automatikusan.

A **Kijelöltek törlése** és **Kijelöltek foglalása** gombok külön műveletlistát indítanak.
A teljes lista és a számlálók a szűrés által elrejtett kijelöléseket is tartalmazzák.
Indításkor a felület a pontos dátumot, raktárt, neveket és slotokat megerősítésre megmutatja.
Nincs alternatív slotválasztás vagy automatikus áthelyezés. Egy kérés legfeljebb 100 tétel.

## Végrehajtás

- Új végpontok: `POST /api/coordinator/schedule/batches`, `GET /api/coordinator/schedule/batches/{uuid}`.
- Csak a meglévő koordinátori/admin jogosultsággal, a felhasználó raktárkorlátozásával érhetők el.
- Kérésenként egy UUID, egy nap, egy raktár és egy művelettípus. Duplikált tételt nem fogadunk el.
- Privát műveleti napló: `pwa-attachments/schedule-bulk-actions/<uuid>.json`.
- Egy mentett listát a `pwa-schedule-bulk.yml` workflow hajt végre. A worker sorban futtatja
  a meglévő, pontos slotra célzott Hub foglalási/törlési parancsokat.
- Futás előtt naplózza a tételt. Megszakadt/megkezdett listát nem játszik le újra automatikusan.
- Azonos UUID ismételt beküldése nem indít második feladatot. Elveszett válasz után azonosító szerinti lekérdezés történik.
- Az eredmény tételes: sikeres, sikertelen, ellenőrizendő. A HTTP 200 melletti OVERLAP nem siker.
- Sikeres tételek kikerülnek a kijelölésből, sikertelenek megmaradnak. Bizonytalan tételek is kikerülnek:
  ezeket az aktuális Hub állapot ellenőrzése nélkül nem próbálja újra a rendszer.
- A napi Hub- és kapacitásadat frissül a végén. A frissítés hibáját külön jelzi.
- A folyamatban lévő kérésazonosítók helyben tárolódnak, így az oldal újranyitásakor
  az állapotlekérdezés folytatható új beküldés nélkül.
- A GitHub-végállapot ellenőrzése a pontos UUID-t tartalmazó futásnévhez kötött;
  más futár feladatának sikere nem lesz ennek a listának a sikere.

## Élesítés és tesztelés

Az új GitHub workflow-nak és a PWA szerverkódnak együtt kell elérhetővé válnia.
A meglévő Hub/GitHub/Supabase beállításokat használja, új SQL migráció nincs.

Offline tesztek: `tests/test_schedule_bulk.py`, `tests/test_schedule_bulk_ui.cjs`.
A böngészős tesztekben minden külső művelet helyettesített: nincs éles Hub törlés/foglalás
vagy GitHub workflow-indítás.

## Külön Hub-frissítés

A beosztás fejlécében a **Hub adatok frissítése** gomb külön szinkront indít.
Ötnapos nézetben a mai és következő négy napra, az engedélyezett raktárakra fut;
napi részletnézetben a kiválasztott napra és raktárra. A régi **Frissítés** gomb
továbbra is a mentett adatok újraolvasása.

Az új `pwa-schedule-refresh.yml` workflow kizárólag Hub műszakblokkokat, foglalásokat,
résztvevőket és a PWA kapacitásösszesítőt frissíti. Nem indít foglalást vagy törlést.
A státuszlekérdezés a kérés UUID-jét tartalmazó pontos futásnevet követi;
csak sikeresen befejezett szinkron után jelzi a frissítés sikerét és tölti újra a nézetet.
A folyamatban lévő kérésazonosító oldalfrissítés után is visszaolvasható.

Új végpontok: `POST /api/coordinator/schedule/hub-refresh`,
`GET /api/coordinator/schedule/hub-refresh/{uuid}`.
A workflow és a szerverkód együtt élesítendő. A fejlesztés során valódi szinkron nem indult.

## Nézetválasztás és stabil megjelenítés

- A Beosztás menü megnyitásakor mindig az ötnapos áttekintés indul.
- A fejlécben a hónap- és raktárválasztó látható. **Összes**: az öt nap;
  **BUD1/BUD2**: a kiválasztott raktár teljes havi naptára, minden naptári nappal.
- Napi részletből visszalépve az eredeti áttekintés marad meg (havi vagy ötnapos).
- Havi nézetben a Hub-frissítés a kiválasztott teljes hónapra/raktárra fut.
- A globális időzítő nem tölti újra az interaktív beosztást. A menü, választók,
  Frissítés gomb és a befejezett Hub-műveletek indítanak adatbetöltést.
- Tömeges feladat közben csak a státusz szövege változik; a napi slotlista nem
  rajzolódik újra három másodpercenként.
- Az indokolt napi újrarajzolás megőrzi a látható slothoz tartozó görgetési helyet,
  nyitott slotokat, érvényes futárválasztást és a kereső fókuszát/kurzorpozícióját.
