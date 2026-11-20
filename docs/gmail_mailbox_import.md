# Gmail-import: Balázs és a system postaláda

A meglévő **Import complaint email responses** workflow mindkét postaládából
ugyanazt a két importot végzi: a „Panasz elbírálva” tárgyú döntéseket és a
`koordinator@jitt.hu` feladótól érkező késés/távolmaradás értesítéseket.
Nem készít piszkozatot és nem küld levelet.

## OAuth a system@jitt.hu fiókhoz

1. Engedélyezd a Gmail API-t az OAuth-kliens Google Cloud projektjében.
2. Web application kliensnél az **Authorized JavaScript origins** üres
   sorát töröld; ehhez a beállításhoz nem szükséges origin.
3. Az **Authorized redirect URIs** mezőbe ezt add meg:
   `https://developers.google.com/oauthplayground`.
4. A kliens létrehozása után az OAuth Playground fogaskerekénél jelöld be
   a **Use your own OAuth credentials** lehetőséget, és add meg a kliens
   azonosítóját és titkát. Az **Access type** legyen **Offline**.
5. Az engedélyezendő scope: `https://www.googleapis.com/auth/gmail.readonly`.
   **Authorize APIs** után a `system@jitt.hu` fiókkal engedélyezz.
6. **Exchange authorization code for tokens** után a **refresh token**
   értékét használd, nem a rövid élettartamú access tokent.

Workspace belső alkalmazásnál az Audience lehet **Internal**, ha a projekt
szervezete ezt engedi. Külső, Testing állapotú alkalmazásnál a Gmailhez
kiadott refresh token 7 nap után lejárhat; tartós futáshoz a megfelelő
éles/belső OAuth-konfiguráció szükséges.

Források: [OAuth Playground](https://developers.google.com/oauthplayground/),
[Google OAuth](https://developers.google.com/identity/protocols/oauth2),
[Gmail jogosultságok](https://developers.google.com/workspace/gmail/api/auth/scopes).

## GitHub Actions secrets

A repository **Settings → Secrets and variables → Actions** felületén:

| Beállítás | Balázs meglévő kulcsa | system új kulcsa |
| --- | --- | --- |
| Client ID | `GMAIL_COMPLAINT_CLIENT_ID` | `GMAIL_SYSTEM_CLIENT_ID` |
| Client secret | `GMAIL_COMPLAINT_CLIENT_SECRET` | `GMAIL_SYSTEM_CLIENT_SECRET` |
| Refresh token | `GMAIL_COMPLAINT_REFRESH_TOKEN` | `GMAIL_SYSTEM_REFRESH_TOKEN` |

A meglévő Balázs-kulcsokat ne írd felül. A system refresh tokennek a
`system@jitt.hu` fiók engedélyezéséből kell származnia. A program a Gmail
profilvégpontján ellenőrzi a postaládát a levelek lekérése előtt.

A workflow a kiválasztott fiók kulcsait közös belső
`GMAIL_COMPLAINT_*` környezeti neveken adja át a scriptnek; egy job csak a
saját fiókja három OAuth-kulcsát kapja meg. Helyi futtatáskor ugyanezekre a
belső nevekre kell beállítani a kiválasztott postaláda hitelesítő adatait.
A kulcsok ne kerüljenek Gitbe, naplóba vagy parancssori argumentumba.

## Futtatás és tárolás

A schedule 15 percenkénti indítást kér (óra 04, 19, 34, 49 percében).
A GitHub ütemezett futásai késhetnek. Két postaláda × két típus = négy job.
A még be nem állított fiókot az ütemezett futás külön figyelmeztetéssel
kihagyja; a másik fiók importja ettől működhet. Kézi indításkor a hiányzó
OAuth-beállítás hibát eredményez.

Első ellenőrzés: **Actions → Import complaint email responses → Run workflow**,
`mailbox = system@jitt.hu`, `dry_run = true`. Ez a Google-hozzáférést és a
találatokat ellenőrzi, adatbázisba nem ment. Utána ugyanígy indítható
`dry_run = false` értékkel az import.

A meglévő táblák változatlanok: `public.complaint_email_responses` és
`public.coordinator_shift_email_notices`. A `(mailbox, gmail_id)` elsődleges
kulcs miatt a két postaláda adatai elkülönülnek, az ismételt futás pedig
nem szúrja be újra ugyanazt a levelet ugyanabból a postaládából.
Ehhez a bővítéshez nem szükséges új SQL-migráció.

Az importált levelek önmagukban nem módosítanak futár-elszámolást, nem
zárnak le reklamációt és nem jelentenek automatikus elfogadást.
