# Admin kapunyitás

A PWA Kapunyitás menüjét kizárólag `admin` és `superadmin` szerepkör látja.
A GET `/api/admin/gate` és POST `/api/admin/gate/open` végpontokon is kötelező a bejelentkezés és ugyanez a szerepkör.
Az admin előnézetben kiválasztott futár nem módosítja ezt a jogosultságot.

## Render Environment beállítások

- `TWILIO_ACCOUNT_SID`: a Twilio fiók AC kezdetű azonosítója.
- `TWILIO_AUTH_TOKEN`: a Twilio titkos tokenje. Kizárólag szerveroldalon tárolandó.
- `TWILIO_GATE_TO`: opcionális, alapértéke `+36501213800`.
- `TWILIO_GATE_FROM`: opcionális, alapértéke `+4915888623971`. A Twilio fiókból hívható hívószám legyen.
- `TWILIO_GATE_TWIML_URL`: opcionális, alapértéke a megadott minta: `https://webhooks.twilio.com/v1/Voice/Template/voice_speech_recognition`.

A requirements.txt tartalmazza a Twilio SDK-t. A hitelesítők nélkül a gomb inaktív.
A céltelefonszámot és a TwiML URL-t a böngésző nem adhatja meg a híváskérésben.
A mintában szereplő TwiML beszédfelismerési sablon; ezt később a kívánt kapunyitó hívásfolyamatra lehet cserélni a környezeti változóval.

## Visszajelzés és ismétlések

A gomb valódi telefonhívást kezdeményez. A folyamat alatt betöltő párbeszédablak látszik,
és új kattintás nem küld új kérést. A sikerüzenet csak a Twilio híváskérés elfogadását
igazolja; a kapu fizikai állapotát az alkalmazás nem méri.

A szerver 60 másodperces közös várakozást alkalmaz. A kérés UUID-jával azonos kérés
egy órán belül nem indít még egy hívást, bizonytalan hálózati eredménynél sem.
Az SDK nem ismétel automatikusan. Hibánál a Twilio naplót kell ellenőrizni.
Ez a védelem folyamatonként memóriában működik; újraindításkor elvész, több worker
vagy több Render példány esetén nem közös. Ilyen telepítés előtt közös tartós
kérésnapló szükséges. A fejlesztői tesztek kizárólag mockolt hívásokat használnak.

Twilio hivatkozás: https://www.twilio.com/docs/voice/api/call-resource
