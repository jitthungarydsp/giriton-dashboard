begin;

create table if not exists public.courier_route_alerts (
    id uuid primary key default gen_random_uuid(),
    courier_id integer not null,
    courier_name text not null,
    route_id text not null,
    order_id text,
    alert_type text not null default 'problem'
        check (alert_type in ('problem', 'delay', 'bag_missing')),
    message text,
    dispatcher_notified boolean not null default false,
    current_address text,
    current_checkpoint_position integer,
    warehouse text,
    route_departure text,
    route_return text,
    status text not null default 'new',
    email_sent_at timestamptz,
    created_at timestamptz not null default now()
);

alter table public.courier_route_alerts
    alter column route_id type text using route_id::text,
    add column if not exists warehouse text,
    add column if not exists route_departure text,
    add column if not exists route_return text,
    add column if not exists email_sent_at timestamptz;

create table if not exists public.courier_route_alert_photos (
    id uuid primary key default gen_random_uuid(),
    alert_id text not null,
    file_name text not null,
    mime_type text not null,
    file_size integer not null default 0,
    file_content_base64 text not null,
    uploaded_at timestamptz not null default now()
);

alter table public.courier_route_alert_photos
    alter column alert_id type text using alert_id::text;

create index if not exists courier_route_alerts_courier_route_idx
    on public.courier_route_alerts (courier_id, route_id, created_at desc);

create index if not exists courier_route_alert_photos_alert_idx
    on public.courier_route_alert_photos (alert_id);

grant select, insert, update, delete on public.courier_route_alerts to service_role;
grant select, insert, update, delete on public.courier_route_alert_photos to service_role;

notify pgrst, 'reload schema';

commit;
