create table if not exists public.stg_jitt_invoice_performance_couriers (
    source_name text not null default 'courier_hub_performance_couriers',
    dsp_code text not null default 'JIT',
    dsp_id integer not null default 8,
    warehouse_id integer not null,
    warehouse_code text not null,
    date_from date not null,
    date_to date not null,
    courier_id text not null,
    courier_name text,
    shifts integer,
    orders integer,
    delayed integer,
    delay_percent numeric(10,2),
    late_percent numeric(10,2),
    no_show_percent numeric(10,2),
    compliance_bad_percent numeric(10,2),
    compliance_score_percent numeric(10,2),
    source_compliance_percent numeric(10,2),
    delay_level text,
    compliance_level text,
    raw_table text,
    raw_fetched_at timestamptz,
    raw_row jsonb not null,
    calculated_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (
        source_name,
        dsp_code,
        dsp_id,
        warehouse_id,
        date_from,
        date_to,
        courier_id
    )
);

create index if not exists idx_stg_jitt_invoice_perf_couriers_date
    on public.stg_jitt_invoice_performance_couriers (date_from, date_to);

create index if not exists idx_stg_jitt_invoice_perf_couriers_courier
    on public.stg_jitt_invoice_performance_couriers (courier_id);

create index if not exists idx_stg_jitt_invoice_perf_couriers_warehouse
    on public.stg_jitt_invoice_performance_couriers (warehouse_code);

comment on table public.stg_jitt_invoice_performance_couriers is
'STAGE: Courier Hub performance raw JSON-bol bontott futar teljesitmeny. A compliance_bad_percent a szerzodeses mutato, a compliance_score_percent a feluleten lathato jo pontszam.';

comment on column public.stg_jitt_invoice_performance_couriers.delay_percent is
'Keses arany: delayed / orders * 100, ha az API nem adja meg kozvetlenul.';

comment on column public.stg_jitt_invoice_performance_couriers.compliance_bad_percent is
'Szerzodeses turamegfelelesi mutato: 0.7 * no_show_percent + 0.3 * late_percent.';

comment on column public.stg_jitt_invoice_performance_couriers.compliance_score_percent is
'Feluleten lathato megfelelesi pontszam: 100 - compliance_bad_percent. Pelda: late=11.1%, no-show=0% -> 96.7%.';

create or replace view public.mart_jitt_invoice_performance_latest as
select distinct on (warehouse_id, courier_id)
    *
from public.stg_jitt_invoice_performance_couriers
order by warehouse_id, courier_id, date_to desc, raw_fetched_at desc nulls last;

comment on view public.mart_jitt_invoice_performance_latest is
'MART: legfrissebb Courier Hub performance sor futaronkent es raktaronkent.';
