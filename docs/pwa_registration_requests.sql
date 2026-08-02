create table if not exists public.pwa_registration_requests (
    id bigserial primary key,
    courier_id integer not null unique,
    courier_name text not null,
    phone_number text not null,
    email text not null,
    status text not null default 'new',
    admin_note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_pwa_registration_requests_status
    on public.pwa_registration_requests (status, updated_at desc);

grant select, insert, update on public.pwa_registration_requests to service_role;
grant usage, select on sequence public.pwa_registration_requests_id_seq to service_role;
