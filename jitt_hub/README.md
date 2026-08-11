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

A jelenlegi verzió UI/UX prototípus, demóadatokkal. A következő fejlesztési lépés a Supabase adatkapcsolat, jogosultságkezelés és valósidejű frissítés bekötése.


## Teszt bejelentkezés

- Felhasználónév: `admin@admin.hu`
- Jelszó: `admin123`

Ez a prototípus kliensoldali demóbeléptetést használ. Éles környezetben Supabase Auth vagy más szerveroldali hitelesítés szükséges.
