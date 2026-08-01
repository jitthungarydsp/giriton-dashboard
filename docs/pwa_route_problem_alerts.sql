create table if not exists public.courier_route_alerts (
    id bigserial primary key,
    courier_id integer not null,
    courier_name text,
    route_id text not null,
    order_id text,
    alert_type text not null default 'problem',
    message text not null,
    dispatcher_notified boolean not null default false,
    current_address text,
    current_checkpoint_position integer,
    status text not null default 'new',
    created_at timestamptz not null default now()
);

create index if not exists idx_courier_route_alerts_created_at
    on public.courier_route_alerts (created_at desc);

create index if not exists idx_courier_route_alerts_route
    on public.courier_route_alerts (route_id, courier_id);

create index if not exists idx_courier_route_alerts_status
    on public.courier_route_alerts (status, created_at desc);

grant select, insert, update on public.courier_route_alerts to service_role;
grant usage, select on sequence public.courier_route_alerts_id_seq to service_role;
