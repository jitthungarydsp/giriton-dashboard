-- Courier card precomputed statistics.
-- One row = one courier for one selected month.
-- Run this in Supabase SQL Editor.

create table if not exists public.courier_card_stats (
    id uuid primary key default gen_random_uuid(),
    snapshot_month text not null,
    period_start date not null,
    period_end date not null,
    generated_at timestamptz not null default now(),
    courier_id text not null,
    name text,
    warehouse text,
    delivered_orders numeric default 0,
    total_orders numeric default 0,
    routes numeric default 0,
    worked_days numeric default 0,
    avg_orders_per_route numeric default 0,
    avg_routes_per_workday numeric default 0,
    avg_wait_minutes numeric default 0,
    late_shift_count numeric default 0,
    planned_shift_count numeric default 0,
    avg_route_minutes numeric default 0,
    avg_loading_minutes numeric default 0,
    avg_planned_loading_minutes numeric default 0,
    avg_real_loading_minutes numeric default 0,
    total_address_count numeric default 0,
    early_address_count numeric default 0,
    late_address_count numeric default 0,
    early_address_rate numeric default 0,
    late_address_rate numeric default 0,
    normal_address_count numeric default 0,
    express_address_count numeric default 0,
    normal_address_rate numeric default 0,
    express_address_rate numeric default 0,
    normal_early_address_count numeric default 0,
    normal_late_address_count numeric default 0,
    express_early_address_count numeric default 0,
    express_late_address_count numeric default 0,
    normal_late_address_rate numeric default 0,
    express_late_address_rate numeric default 0,
    normal_routes numeric default 0,
    express_routes numeric default 0,
    estimated_max_revenue numeric default 0,
    avg_revenue_per_route numeric default 0,
    previous_month_revenue numeric default 0,
    source_name text not null default 'courier-card-db',
    created_at timestamptz not null default now(),

    constraint courier_card_stats_unique
        unique (snapshot_month, courier_id)
);

create index if not exists idx_courier_card_stats_month
    on public.courier_card_stats (snapshot_month);

create index if not exists idx_courier_card_stats_courier
    on public.courier_card_stats (courier_id);
