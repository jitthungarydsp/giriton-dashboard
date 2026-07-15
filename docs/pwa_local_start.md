# Giriton Futár PWA – helyi indítás

## Beállítás

A PWA a meglévő `data/users.json` felhasználóit és Supabase-konfigurációját használja.
A `.streamlit/secrets.toml` fájlba kerüljön egy hosszú, véletlenszerű titok:

```toml
SUPABASE_URL = "https://projekt.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "service-role-kulcs"
PWA_SESSION_SECRET = "legalabb-32-karakteres-veletlen-ertek"
```

A munkamenet sütije helyi HTTP-n fejlesztői, éles HTTPS-en automatikusan biztonságos
(`Secure`) módban működik.

Helyi fejlesztéskor a `PWA_SESSION_SECRET` elhagyható: az alkalmazás automatikusan
létrehoz egy Git által figyelmen kívül hagyott `.pwa_session_secret` fájlt. Éles
környezetben mindig környezeti változóként vagy a secrets fájlban add meg.

## Indítás

```powershell
pip install -r requirements.txt
uvicorn pwa_api:app --host 0.0.0.0 --port 8080 --reload
```

Ezután nyisd meg a telefonon vagy a böngészőben:

```text
http://localhost:8080
```

Azonos Wi-Fi hálózaton a számítógép helyi IP-címével telefonról is megnyitható,
például `http://192.168.1.20:8080`. A tényleges PWA-telepítéshez az éles környezetben
HTTPS szükséges.

## Render telepítés

A gyökérben található `render.yaml` létrehoz egy ingyenes Python webszolgáltatást,
amely a `main` ág változásait automatikusan telepíti. A Blueprint első létrehozásakor
a Render felületén kell megadni a `SUPABASE_URL` és `SUPABASE_SERVICE_ROLE_KEY`
értékeket. A `PWA_SESSION_SECRET` értékét a Render automatikusan generálja.

A szolgáltatás indítási parancsa:

```text
uvicorn pwa_api:app --host 0.0.0.0 --port $PORT
```
