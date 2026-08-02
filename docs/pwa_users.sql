create table if not exists public.pwa_users (
    id bigserial primary key,
    courier_id integer not null unique,
    username text not null,
    email text,
    role text not null default 'user',
    active boolean not null default true,
    password_hash text not null,
    password_updated_at timestamptz,
    credential_email_sent_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists idx_pwa_users_username_lower
    on public.pwa_users (lower(trim(username)));

create index if not exists idx_pwa_users_active_courier
    on public.pwa_users (active, courier_id);

grant select, insert, update on public.pwa_users to service_role;
grant usage, select on sequence public.pwa_users_id_seq to service_role;
