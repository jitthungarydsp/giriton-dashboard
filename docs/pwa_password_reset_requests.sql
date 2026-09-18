create table if not exists public.pwa_password_reset_requests (
    id bigserial primary key,
    courier_id integer not null,
    courier_name text,
    email text not null,
    status text not null default 'new'
        check (status in ('new', 'sent', 'rejected')),
    admin_note text,
    sent_at timestamptz,
    sent_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_pwa_password_reset_requests_status
    on public.pwa_password_reset_requests (status, updated_at desc);

create index if not exists idx_pwa_password_reset_requests_courier
    on public.pwa_password_reset_requests (courier_id, created_at desc);

grant select, insert, update on public.pwa_password_reset_requests to service_role;
grant usage, select on sequence public.pwa_password_reset_requests_id_seq to service_role;
