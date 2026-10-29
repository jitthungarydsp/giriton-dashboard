# Szeptemberi Excel – hiányzó paraméterillesztések

2038 túrasor és 68 ügyfélértékelési sor ellenőrzése. A jelenlegi aktív, nem törölt paramétereket a dátum, túratípus, napbesorolás és raktár alapján illesztettük. A REGION elnevezést regional típusra egységesítettük.

| Ellenőrzés | Nem illeszkedő sor |
|---|---:|
| Alapdíj | 0 |
| Késedelmi bónusz | 0 |
| Túramegfelelés | 50 |
| Ügyfélértékelés – sávok közötti rés | 4 |
| Ügyfélértékelés – legalacsonyabb fizető sáv alatt | 6 |

A 6 alacsony értékelést nem tekintjük paraméterhibának: a jelenlegi szabályok szerint nincs rájuk pozitív bónusz. A 4 köztes érték viszont a két tizedesre megadott sávok között marad: 4,899; 4,895; 4,797; 4,795. A jelenlegi kód nem kerekíti ezeket illesztés előtt.

A túramegfelelés 50 sora 9 futárt érint: 47 expressz × 666 Ft és 3 regionális × 916 Ft. Ezek céges Excel-értékek, nem automatikusan a futárnak járó összegek.

## Érintett túrák

| Excel sor | Futár | Dátum | Túra ID | Típus | Mező | Excel érték |
|---:|---|---|---|---|---|---:|
| 84 | Vándor Balázs | 2026-09-03 | 1529065 | express | Compliance Bonus | 666 |
| 87 | Vándor Balázs | 2026-09-03 | 1529120 | express | Compliance Bonus | 666 |
| 95 | Vándor Balázs | 2026-09-03 | 1529265 | express | Compliance Bonus | 666 |
| 99 | Vándor Balázs | 2026-09-03 | 1529356 | express | Compliance Bonus | 666 |
| 106 | Vándor Balázs | 2026-09-03 | 1529477 | express | Compliance Bonus | 666 |
| 111 | Vándor Balázs | 2026-09-03 | 1529618 | express | Compliance Bonus | 666 |
| 112 | Nagy Kristóf | 2026-09-03 | 1529644 | express | Compliance Bonus | 666 |
| 114 | Vándor Balázs | 2026-09-03 | 1529651 | express | Compliance Bonus | 666 |
| 116 | Tuza Ádám | 2026-09-03 | 1529657 | express | Compliance Bonus | 666 |
| 133 | Abonyi György | 2026-09-04 | 1530032 | express | Compliance Bonus | 666 |
| 163 | Tuza Ádám | 2026-09-04 | 1530635 | express | Compliance Bonus | 666 |
| 310 | Cserna Levente Zoltán | 2026-09-08 | 1533875 | regional | Compliance Bonus | 916 |
| 352 | Vándor Balázs | 2026-09-09 | 1534635 | express | Compliance Bonus | 666 |
| 358 | Vándor Balázs | 2026-09-09 | 1534757 | express | Compliance Bonus | 666 |
| 390 | Cserna Levente Zoltán | 2026-09-10 | 1535324 | regional | Compliance Bonus | 916 |
| 412 | Cserna Levente Zoltán | 2026-09-10 | 1535760 | regional | Compliance Bonus | 916 |
| 433 | Kiss 7245 Csaba | 2026-09-10 | 1536109 | express | Compliance Bonus | 666 |
| 483 | Tuza Ádám | 2026-09-11 | 1537171 | express | Compliance Bonus | 666 |
| 484 | Abonyi György | 2026-09-11 | 1537175 | express | Compliance Bonus | 666 |
| 611 | Abonyi György | 2026-09-14 | 1540082 | express | Compliance Bonus | 666 |
| 613 | Abonyi György | 2026-09-14 | 1540106 | express | Compliance Bonus | 666 |
| 628 | Vándor Balázs | 2026-09-15 | 1540442 | express | Compliance Bonus | 666 |
| 637 | Vándor Balázs | 2026-09-15 | 1540610 | express | Compliance Bonus | 666 |
| 646 | Vándor Balázs | 2026-09-15 | 1540885 | express | Compliance Bonus | 666 |
| 674 | Nagy Kristóf | 2026-09-16 | 1541566 | express | Compliance Bonus | 666 |
| 736 | Abonyi György | 2026-09-17 | 1543102 | express | Compliance Bonus | 666 |
| 863 | Kiss 7245 Csaba | 2026-09-20 | 1546326 | express | Compliance Bonus | 666 |
| 921 | Vándor Balázs | 2026-09-22 | 1547731 | express | Compliance Bonus | 666 |
| 926 | Nagy Kristóf | 2026-09-22 | 1547822 | express | Compliance Bonus | 666 |
| 932 | Vándor Balázs | 2026-09-22 | 1547962 | express | Compliance Bonus | 666 |
| 933 | Nagy Kristóf | 2026-09-22 | 1547981 | express | Compliance Bonus | 666 |
| 937 | Abonyi György | 2026-09-22 | 1548070 | express | Compliance Bonus | 666 |
| 939 | Vándor Balázs | 2026-09-22 | 1548116 | express | Compliance Bonus | 666 |
| 953 | Tuza Ádám | 2026-09-22 | 1548369 | express | Compliance Bonus | 666 |
| 1123 | Tuza Ádám | 2026-09-26 | 1552645 | express | Compliance Bonus | 666 |
| 1141 | Vándor Balázs | 2026-09-27 | 1553046 | express | Compliance Bonus | 666 |
| 1168 | Vándor Balázs | 2026-09-27 | 1553532 | express | Compliance Bonus | 666 |
| 1179 | Vándor Balázs | 2026-09-27 | 1553695 | express | Compliance Bonus | 666 |
| 1180 | Kiss 7245 Csaba | 2026-09-27 | 1553704 | express | Compliance Bonus | 666 |
| 1254 | Vándor Balázs | 2026-09-29 | 1555202 | express | Compliance Bonus | 666 |
| 1263 | Vándor Balázs | 2026-09-29 | 1555412 | express | Compliance Bonus | 666 |
| 1273 | Vándor Balázs | 2026-09-29 | 1555576 | express | Compliance Bonus | 666 |
| 1288 | Vándor Balázs | 2026-09-29 | 1555897 | express | Compliance Bonus | 666 |
| 1652 | Kanyó Krisztián | 2026-09-15 | 1540370 | express | Compliance Bonus | 666 |
| 1653 | Koncsik Zoltán | 2026-09-15 | 1540478 | express | Compliance Bonus | 666 |
| 1738 | Kanyó Krisztián | 2026-09-18 | 1543880 | express | Compliance Bonus | 666 |
| 1921 | Lulaj 8001 Brendon | 2026-09-25 | 1551454 | express | Compliance Bonus | 666 |
| 1967 | Kanyó Krisztián | 2026-09-27 | 1553463 | express | Compliance Bonus | 666 |
| 2008 | Koncsik Zoltán | 2026-09-29 | 1555259 | express | Compliance Bonus | 666 |
| 2033 | Koncsik Zoltán | 2026-09-30 | 1556356 | express | Compliance Bonus | 666 |

## Értékelési sávok közötti rések

| Excel sor | Futár ID | Értékelés |
|---:|---|---:|
| 37 | 7245 | 4.899 |
| 38 | 8226 | 4.895 |
| 57 | 8864 | 4.797 |
| 58 | 8760 | 4.795 |

Ez szabályillesztési vizsgálat, nem a tényleges kifizetések ellenőrzése. Egyes hiányzó túraszintű bónuszokat kézi korrekció pótolhat. Az Excel egyedi bónusz-, levonás- és ATM-lapjai közvetlen tételek; ezekhez nem ugyanilyen díjszabály-illesztést kell végezni. Nem állítjuk, hogy ez a vizsgálat az összes egyedi elszámolási jogosultsági szabályt, például a lojalitást is újraszámolta. Éles adat nem módosult.
