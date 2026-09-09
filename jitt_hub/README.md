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
