# Kezelendő elszámolási paraméterillesztések – 2026. szeptember

Állapot: nyitott, javításra vár. Rögzítve: 2026-10-29, a felhasználó kérésére.

Forrás: JIT_2026.IX.xlsx, 2038 túrasor és 68 ügyfélértékelési sor vizsgálata a vizsgálatkor aktív paraméterekkel. Az Excel és az éles adatbázis nem módosult.

## Megállapítások

- Alapdíj: 0 nem illeszkedő túrasor.
- Késedelmi bónusz: 0 nem illeszkedő túrasor.
- Túramegfelelés: 50 nem illeszkedő túrasor, 9 futár.
  - 47 expressz túra: Excel Compliance Bonus = 666 Ft; az aktív LEVEL-2 paraméter cégösszege 750 Ft, futárösszege 500 Ft, ezért a pontos összegillesztés nem talál szabályt.
  - 3 regionális túra: Excel Compliance Bonus = 916 Ft; Cserna Levente Zoltán, szeptember 8. és 10.; az illeszkedő regionális szabály szeptember 11-től érvényes. Excel-sorok: 310, 390, 412.
- Ügyfélértékelés: 4 érték a paramétersávok között marad:
  - ID 7245: 4,899, értékelési lap 37. sor.
  - ID 8226: 4,895, 38. sor.
  - ID 8864: 4,797, 57. sor.
  - ID 8760: 4,795, 58. sor.
- További 6 értékelés a legalacsonyabb bónuszsáv alatti; ezeket nem minősítettük paraméterhibának.

Összesen 54 ellenőrzendő forrássor. Ez nem azonos 54 igazolt elmaradt kifizetéssel: kézi korrekciók pótolhatták az összegeket.

## Érintett futárok – túramegfelelés

| Futár | Túrasor |
|---|---:|
| Vándor Balázs | 22 |
| Abonyi György | 6 |
| Tuza Ádám | 5 |
| Nagy Kristóf | 4 |
| Cserna Levente Zoltán | 3 |
| Kanyó Krisztián | 3 |
| Kiss 7245 Csaba | 3 |
| Koncsik Zoltán | 3 |
| Lulaj 8001 Brendon | 1 |

## Teendők

- [ ] Jóváhagyni az expressz 666 Ft-os forrásértékhez tartozó futárösszeget és annak érvényességi idejét.
- [ ] Tisztázni a regionális 916 Ft-os szabály szeptember 11. előtti alkalmazhatóságát.
- [ ] Egyértelműsíteni az értékelési sávhatárokat és a három tizedesjegy kezelését.
- [ ] Futáronként ellenőrizni a korábban rögzített pótló kézi korrekciókat; az újraszámítás ne adja hozzá még egyszer ugyanazt a pótlást.
- [ ] Jóváhagyott paraméterekkel újraszámolni az érintett elszámolásokat, és az előző eredményhez képesti eltérést megmutatni.
- [ ] A nem illeszkedő pozitív forrásértékeket feltűnő ellenőrzési hibaként jelezni; a 0 Ft-os eredmény ne fedje el a hiányzó szabályt.

## Megőrzött bizonyítékok

A tételes, Excel-sorszámokat tartalmazó lista és a strukturált vizsgálati eredmény ugyanebben a mappában:

- settlement_parameter_issues_2026_09_details.md
- settlement_parameter_issues_2026_09_audit.json

A listák a vizsgálat állapotát rögzítik. Az éles paraméterek javítása vagy az elszámolások módosítása külön feladat.
