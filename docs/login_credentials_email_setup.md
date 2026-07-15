# Belépési adatok küldése e-mailben

Az Admin oldalon a kiválasztott futárnak új ideiglenes jelszó készíthető és
elküldhető a felhasználónévvel együtt. A rendszer a korábbi jelszót nem küldi
ki. Sikertelen SMTP-küldéskor a jelszóváltoztatást visszaállítja.

## Szükséges Streamlit secretek

```toml
SMTP_HOST = "smtp.example.com"
SMTP_PORT = "587"
SMTP_USERNAME = "noreply@example.com"
SMTP_PASSWORD = "smtp-jelszo-vagy-app-password"
SMTP_FROM_EMAIL = "noreply@example.com"
SMTP_FROM_NAME = "Giriton"
SMTP_USE_SSL = "false"
SMTP_USE_STARTTLS = "true"
APP_LOGIN_URL = "https://az-alkalmazas-cime.example.com"
```

Gmail SMTP esetén jellemzően `smtp.gmail.com`, STARTTLS mellett `587` port,
SSL mellett `465` port használható. A normál Google-fiókjelszót ne tárold az
alkalmazásban; külön alkalmazásjelszót vagy szervezeti SMTP-hitelesítést használj.

## Admin folyamat

1. Admin -> Felhasználó kezelése.
2. Futár kiválasztása.
3. E-mail-cím ellenőrzése vagy megadása.
4. Jelszóváltoztatás jóváhagyása.
5. Belépési adatok elküldése.

A kiküldött ideiglenes jelszó nincs olvasható formában eltárolva.
