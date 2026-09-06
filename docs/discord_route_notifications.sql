create table if not exists public.discord_route_notifications (
    id bigserial primary key,
    courier_id text not null,
    courier_name text,
    route_id text not null,
    warehouse text,
    order_id text,
    assigned_at timestamptz,
    planned_departure timestamptz,
    planned_return timestamptz,
    notified_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    unique (courier_id, route_id)
);

create index if not exists discord_route_notifications_courier_idx
    on public.discord_route_notifications (courier_id);

create index if not exists discord_route_notifications_notified_at_idx
    on public.discord_route_notifications (notified_at desc);

alter table public.discord_route_notifications
    add column if not exists warehouse text;

alter table public.discord_route_notifications
    add column if not exists licence_plate text;

alter table public.discord_route_notifications
    add column if not exists orders_in_route text;

create index if not exists discord_route_notifications_warehouse_idx
    on public.discord_route_notifications (warehouse);
