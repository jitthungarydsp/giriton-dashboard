# Reklamációk Route ID szerint

A túrához tartozó reklamáció (`cleanedTimeWindowLate`, `uncleanedTimeWindowLate`, a menet közbeni jelzésekből létrehozott ügyekkel együtt) pontosan egy Route ID-t foglalhat le. Ugyanaz a Route ID egyszer szerepelhet új reklamációban, futártól, naptól, hónaptól és kategóriától függetlenül. Másik túra ugyanazon a napon külön ügy. Lezárás nem szabadítja fel az azonosítót. A műszak és no-show folyamat továbbra is nap szerint működik.

## Élesítés sorrendje

1. A meglévő daily-limit és forwarding/browser-approval SQL-ek után futtasd: `sql/pwa_quality_complaint_route_limit.sql`.
2. Utána kerülhet ki a v299 PWA és az API. Az API az új `pwa_find_quality_route_complaint` RPC-t használja; SQL nélkül nem telepíthető önmagában.

A migráció tranzakciós és újrafuttatható. A meglévő reklamációkat és beküldéseket nem írja át. A korábbi duplikációk közül a már beküldött ügy kap elsőbbséget, utána a folyamatban lévő, majd a legrégebbi ügy. A régi, több túrás vagy azonosító nélküli ügy nem továbbítható automatikusan; külön ellenőrzés szükséges. Ha egy régi Google-beküldés más Route ID-val történt, mindkét azonosítót foglaltnak őrizzük meg, és a felület jelzi az eltérést.

A Route ID már a csukott kártyán látható. A továbbított kártya a mentett Google-payload azonosítóját mutatja. Az ugyanerre a túrára érkezett másik jelzésből a már létező ügy nyílik meg, a nyers jelzés pedig külön, naplózott duplikációs lezárással rendezhető.

A „Még nincs reklamáció · Route ID” szűrő azokat az azonosítható túrajelzéseket mutatja, amelyeknek nincs mentett ügyük; a fejléc külön számolja a jelzéseket és az egyedi túrákat. A „Rögzítve · továbbításra vár” szűrő a nyitott, még nem beküldött ügyeket mutatja. A `scripts/audit_quality_route_coverage.py --month 2026-11 --output <könyvtár>` csak olvasással, a hiteles Route ID-foglalásokból készít HTML- és JSON-kimutatást.

## Ellenőrzés

`tests/test_quality_route_limit_sql.cjs` izolált PostgreSQL-adatbázisban (@electric-sql/pglite a NODE_PATH-on) ellenőrzi a teljes migrációt, a történeti rekordok megőrzését, a Route ID ütközéseket, az aznapi eltérő túrákat, a továbbítás és az identitás védelmét, valamint az újrafuttatást. A többi quality teszt az API-, felület- és piszkozatkezelést ellenőrzi.
