create schema if not exists settlement;

create table if not exists settlement.email_templates (
    template_key text primary key,
    template_name text not null,
    subject text not null,
    body text not null,
    is_active boolean not null default true,
    updated_by text not null default 'system',
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create table if not exists settlement.courier_email_log (
    id bigserial primary key,
    courier_id text not null default '',
    courier_name text not null default '',
    recipient_email text not null default '',
    template_key text not null default '',
    subject text not null default '',
    body text not null default '',
    status text not null default 'sent',
    error_message text not null default '',
    sent_by text not null default 'system',
    context jsonb not null default '{}'::jsonb,
    sent_at timestamptz not null default now()
);

create index if not exists courier_email_log_courier_month_idx
    on settlement.courier_email_log (courier_id, sent_at desc);

insert into settlement.email_templates (template_key, template_name, subject, body, is_active, updated_by)
values
    ('new_settlement', 'Új elszámolás érkezett', 'Új elszámolásod érkezett',
     'Kedves {courier_name}!

Új elszámolásod érkezett a JITT felületén.
Hónap: {month}

Itt tudod megnézni:
{login_url}

Üdvözlettel:
JITT', true, 'system'),
    ('settlement_accepted', 'Elszámolás elfogadva', 'Elszámolás elfogadva',
     'Kedves {courier_name}!

Rögzítettük, hogy elfogadtad az elszámolásodat.
Hónap: {month}
Összeg: {amount_huf}

Üdvözlettel:
JITT', true, 'system'),
    ('tig_accepted', 'TIG elfogadva', 'TIG elfogadva',
     'Kedves {courier_name}!

Rögzítettük, hogy elfogadtad a TIG-et.
Hónap: {month}
TIG végösszeg: {amount_huf}

Üdvözlettel:
JITT', true, 'system'),
    ('document_uploaded', 'Új dokumentum', 'Új dokumentumod érkezett',
     'Kedves {courier_name}!

Új dokumentum érkezett a JITT felületén.
Típus: {document_type}
Hónap: {month}
Dokumentum: {document_title}

Itt tudod megnézni:
{login_url}

Üdvözlettel:
JITT', true, 'system'),
    ('complaint_response', 'Reklamáció válasz', 'Válasz érkezett a reklamációdra',
     'Kedves {courier_name}!

Válasz érkezett a reklamációdra.
Hónap: {month}

Válasz:
{admin_message}

Üdvözlettel:
JITT', true, 'system'),
    ('payment_rejected', 'Kifizetés elutasítva / visszanyitva', 'Kifizetés státusza módosult',
     'Kedves {courier_name}!

A kifizetésed státusza módosult.
Hónap: {month}

Megjegyzés:
{status_note}

Üdvözlettel:
JITT', true, 'system'),
    ('free_text', 'Szabad szöveges e-mail', 'JITT üzenet',
     'Kedves {courier_name}!

{free_text}

Üdvözlettel:
JITT', true, 'system'),
    ('status_settlement_missing', 'Státusz - elszámolásra vár', 'Elszámolás előkészítés alatt',
     'Kedves {courier_name}!

A {month} havi elszámolásod még előkészítés alatt van.
Amint elérhető lesz, a PWA felületen látni fogod.

Belépés:
{login_url}

Üdvözlettel:
JITT', true, 'system'),
    ('status_settlement_acceptance_waiting', 'Státusz - elszámolás elfogadásra vár', 'Elfogadásra vár az elszámolásod',
     'Kedves {courier_name}!

A {month} havi elszámolásod elfogadásra vár.
Kérjük, nézd át és fogadd el a PWA felületen.

Belépés:
{login_url}

Üdvözlettel:
JITT', true, 'system'),
    ('status_tig_missing', 'Státusz - TIG-re vár', 'A TIG előkészítés alatt van',
     'Kedves {courier_name}!

A {month} havi TIG még előkészítés alatt van.
Amint elkészül, a PWA felületen fogod látni.

Üdvözlettel:
JITT', true, 'system'),
    ('status_tig_acceptance_waiting', 'Státusz - TIG elfogadásra vár', 'Elfogadásra vár a TIG-ed',
     'Kedves {courier_name}!

A {month} havi TIG-ed elfogadásra vár.
Kérjük, nézd át és fogadd el a PWA felületen.

Belépés:
{login_url}

Üdvözlettel:
JITT', true, 'system'),
    ('status_invoice_upload_waiting', 'Státusz - számlafeltöltésre vár', 'Számlafeltöltés szükséges',
     'Kedves {courier_name}!

A {month} havi folyamatod számlafeltöltésre vár.
Kérjük, töltsd fel a számlát a PWA felületen.
Várt összeg: {amount_huf}

Belépés:
{login_url}

Üdvözlettel:
JITT', true, 'system'),
    ('status_invoice_check_waiting', 'Státusz - számlaellenőrzésre vár', 'A számlád ellenőrzés alatt van',
     'Kedves {courier_name}!

A {month} havi számlád ellenőrzés alatt van.
Ha szükség lesz javításra, külön jelezni fogjuk.

Üdvözlettel:
JITT', true, 'system'),
    ('status_complaint_open', 'Státusz - bejelentések', 'Nyitott bejelentésed van',
     'Kedves {courier_name}!

A {month} havi folyamatodban nyitott bejelentés szerepel.
Amint válasz érkezik rá, értesítünk.

Üdvözlettel:
JITT', true, 'system'),
    ('status_salary_advance_open', 'Státusz - új fizetés előleg', 'Fizetés előleg igénylésed nyitva van',
     'Kedves {courier_name}!

A fizetés előleg igénylésed nyitott státuszban van.
A feldolgozás állapotát a PWA felületen tudod követni.

Üdvözlettel:
JITT', true, 'system'),
    ('status_payment_waiting', 'Státusz - kifizetésre vár', 'Kifizetésre vár a havi folyamatod',
     'Kedves {courier_name}!

A {month} havi folyamatod kifizetésre vár.
Aktuális összeg: {amount_huf}

Üdvözlettel:
JITT', true, 'system'),
    ('status_paid', 'Státusz - kifizetve', 'A havi folyamatod lezárva',
     'Kedves {courier_name}!

A {month} havi folyamatod lezárva, kifizetett státuszban van.
Végösszeg: {amount_huf}

Üdvözlettel:
JITT', true, 'system')
on conflict (template_key) do nothing;

grant usage on schema settlement to service_role;
grant all on settlement.email_templates to service_role;
grant all on settlement.courier_email_log to service_role;
grant usage, select on all sequences in schema settlement to service_role;
