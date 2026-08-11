# Jitt Hub Operations Prototype

Teljes, kattintható frontend prototípus a látványterv alapján.

## Indítás

A legegyszerűbb:

1. Csomagold ki a projektet.
2. Nyisd meg az `index.html` fájlt böngészőben.

Helyi webszerverrel:

```bash
python -m http.server 8080
```

Ezután: `http://localhost:8080`

## Tartalom

- Dashboard
- Műszakok
- Futárok
- Rendelések
- Elszámolások
- Pénzügy
- Importok
- Dokumentumok
- Discord
- Járművek
- Riportok & BI
- Beállítások
- Audit napló

A riport oldal már a `/api/route-quality` végponton keresztül tud Supabase-ből adatot olvasni. A végpont csak belső riport kulccsal válaszol, hogy a futár/műszak/túra adatok ne legyenek nyilvánosan elérhetők.

Cloudflare környezeti változók:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `HUB_REPORT_TOKEN`

A hub felületén a Kimutatás oldalon a `Riport kulcs` mezőbe a `HUB_REPORT_TOKEN` értékét kell megadni.


## Teszt bejelentkezés

- Felhasználónév: `admin@admin.hu`
- Jelszó: `admin123`

Ez a prototípus kliensoldali demóbeléptetést használ. Éles környezetben Supabase Auth vagy más szerveroldali hitelesítés szükséges.
