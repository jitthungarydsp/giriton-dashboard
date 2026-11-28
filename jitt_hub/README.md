# JITT Hub login template

Tiszta bejelentkező oldal sablon a `jitt.hu` alatti Hub indulásához.

## Indítás

Nyisd meg az `index.html` fájlt böngészőben.

## Cloudflare deploy

A repo gyökerében lévő `wrangler.toml` ezt a mappát szolgálja ki:

- Worker entry: `jitt_hub/worker.js`
- Assets directory: `jitt_hub`

Ha Cloudflare Pages képernyőn állítod be:

- Framework preset: `None`
- Build command: üres
- Build output directory: `jitt_hub`

## Tartalom

- Bejelentkező képernyő
- JITT Hub arculati induló felület
- Üres, később beköthető belépési logika

## Következő lépés

Erre kerülhet rá később:

- valódi belépés,
- futár 360 nézet,
- Hub műszakadatok,
- Excel alapú elszámolás.

## Futár 360° élő státuszok

A Futár 360° az aktuális napon 30 másodpercenként lekéri a futár állapotát.
A Worker a Kifli Hubot közvetlenül olvassa a Supabase privát
`hub-session-cache` tárolójában megosztott munkamenettel. Ehhez szolgáltatási
jogosultságú Supabase-kulcs szükséges. A `COURIER_HUB_COOKIE` vagy a
`COURIER_HUB_AUTHORIZATION` közvetlenül is megadható Worker-titokként.
Hiba esetén a felület a mentett állapotot és annak időpontját mutatja.
