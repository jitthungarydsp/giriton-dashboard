create table if not exists public.raw_jitt_invoice_perf_couriers_daily (
    source_name text not null default 'courier_hub_performance_couriers',
    dsp_code text not null default 'JIT',
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    warehouse_code text not null,
    work_date date not null,
    courier_id text not null,
    courier_name text,
    external_carrier_id integer,
    external_carrier_name text,
    external_carrier_short_name text,
    order_count integer,
    route_count integer,
    delayed_order_count integer,
    pct_of_delayed_orders numeric(12, 6),
    shift_count integer,
    late_count integer,
    did_not_come_count integer,
    pct_late_evaluation numeric(12, 6),
    pct_did_not_come_evaluation numeric(12, 6),
    raw_table text not null,
    raw_fetched_at timestamptz,
    raw_row jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (
        source_name,
        dsp_code,
        dsp_id,
        warehouse_id,
        work_date,
        courier_id
    )
);

create index if not exists idx_raw_jitt_invoice_perf_couriers_daily_date
    on public.raw_jitt_invoice_perf_couriers_daily (work_date, warehouse_id);

create index if not exists idx_raw_jitt_invoice_perf_couriers_daily_courier
    on public.raw_jitt_invoice_perf_couriers_daily (courier_id, work_date);

create index if not exists idx_raw_jitt_invoice_perf_couriers_daily_no_show
    on public.raw_jitt_invoice_perf_couriers_daily (work_date, did_not_come_count)
    where did_not_come_count is not null and did_not_come_count > 0;

create index if not exists idx_raw_jitt_invoice_perf_couriers_daily_raw_row
    on public.raw_jitt_invoice_perf_couriers_daily using gin (raw_row);

comment on table public.raw_jitt_invoice_perf_couriers_daily is
    'Courier Hub JITT performance napi futar szintu raw bontas.';
