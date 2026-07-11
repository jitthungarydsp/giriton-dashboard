create table if not exists public.jitt_invoice_performance_bud1_raw (
    source_name text not null default 'courier_hub_performance_couriers',
    dsp_code text not null default 'JIT',
    dsp_id integer not null default 8,
    warehouse_id integer not null default 1,
    warehouse_code text not null default 'BUD1',
    date_from date not null,
    date_to date not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    fetch_batch_id uuid not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (
        source_name,
        dsp_code,
        dsp_id,
        warehouse_id,
        date_from,
        date_to
    )
);

create table if not exists public.jitt_invoice_performance_bud2_raw (
    source_name text not null default 'courier_hub_performance_couriers',
    dsp_code text not null default 'JIT',
    dsp_id integer not null default 8,
    warehouse_id integer not null default 2,
    warehouse_code text not null default 'BUD2',
    date_from date not null,
    date_to date not null,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    fetch_batch_id uuid not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (
        source_name,
        dsp_code,
        dsp_id,
        warehouse_id,
        date_from,
        date_to
    )
);

create index if not exists idx_jitt_invoice_performance_bud1_date
    on public.jitt_invoice_performance_bud1_raw (date_from, date_to);

create index if not exists idx_jitt_invoice_performance_bud2_date
    on public.jitt_invoice_performance_bud2_raw (date_from, date_to);

create index if not exists idx_jitt_invoice_performance_bud1_json
    on public.jitt_invoice_performance_bud1_raw using gin (response_json);

create index if not exists idx_jitt_invoice_performance_bud2_json
    on public.jitt_invoice_performance_bud2_raw using gin (response_json);

create or replace view public.jitt_invoice_performance_raw_all as
select *
from public.jitt_invoice_performance_bud1_raw
union all
select *
from public.jitt_invoice_performance_bud2_raw;
