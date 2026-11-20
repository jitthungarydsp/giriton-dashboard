# PWA jelzéslista

Az admin **Futár reklamációk kezelése** menüjében a reklamációk, a túra közbeni
jelzések és a műszakkésés-jelzések egy listában jelennek meg. A háttérben az
összes adatoldal betöltődik; a felületen nincs lapozás.

A szűrő értékei: **Összes**, **Automatikus jelzés**, **Futár jelzés** és
**Továbbított**. A továbbított rekordok csak az utolsó nézetben látszanak.
A számláló mindig a választott nézet eredményét követi. A továbbítás a
reklamáció mentett `forwarded` állapotát jelenti.

## Duplikáció lezárása

A még önálló nyers jelzésekhez **Lezárás duplikációként** gomb tartozik.
A megerősítő ablakban lehet jóváhagyni vagy megszakítani a műveletet.
Csak reklamációkezelő admin menthet lezárást; a szerver a jelzés forrását,
típusát és az aktuális reklamációs hónapot is ellenőrzi. Már közvetlenül
reklamációhoz kapcsolt jelzést a reklamáció saját felületén kell kezelni.

A lezárás a meglévő `public.peopleforce_card_statuses` táblában, a privát
`internal_complaint_assignment:duplicate-signal:<route|shift>:<jelzés ID>`
kulcson tárolódik. A `status_note` JSON `recordType=qualitySignalResolution`,
`schemaVersion=2`, `reason=duplicate`, `closedAt` és `closedBy` mezőket
tartalmaz. A rekord `status=done`. A már használt privát prefix kizárt a
futár elszámolási munkafolyamatából; a kijelölési e-mail-küldő kizárólag
az 1-es JSON-verziót kezeli, így ezekhez nem küld értesítést.

A nyers jelzés, képei és az eredeti reklamáció megmaradnak. Nem keletkezik
új reklamáció, nem módosul pénzügy, és nincs új migráció. A jelzés csak
igazolt mentés után tűnik el, frissítés és ismételt megnyitás után is.
Az ismételt lezárás ugyanazt az eredeti lezárót és időpontot adja vissza.

## Már létező napi reklamáció

A `pwa_quality_complaint_daily_limit.sql` azonos futárra és napra egy
`address_delay` reklamációt enged. Ha a nyers jelzésből történő létrehozás
ilyen meglévő ügyet talál, a **Reklamáció kezelése / Google-űrlap** gomb
új bejegyzés helyett azt nyitja meg. Továbbított ügy esetén a szűrő is
**Továbbított** nézetre vált. A további nyers jelzés lezárása továbbra is
az admin kifejezett, külön művelete; az eredeti napi reklamáció nem íródik át.
A táskahiányhoz tartozó futárbüntetés nem kerül automatikusan a címkésési
ügyhöz, mert más napi besorolásba tartozik.
