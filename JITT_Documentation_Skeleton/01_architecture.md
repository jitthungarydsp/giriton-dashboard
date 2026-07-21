# 01 Architecture

## Cél

A rendszer réteges felépítésű (UI → Service → Repository → Database).

## Fő modulok

-   Streamlit UI
-   API
-   Billing Engine
-   Comparison Engine
-   Finalization
-   Invoice
-   TIG

## Alapelvek

-   UI nem tartalmaz üzleti logikát.
-   Minden számítás külön Engine-ben történik.
-   Repository csak adatbázis műveleteket végez.
