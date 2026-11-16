-- Futár-hónap szintű elszámolási folyamatmutatók.
-- Futtatás helye: Supabase SQL Editor.

begin;

create extension if not exists pgcrypto;

alter table settlement.monthly_process_metric_summary
    add column if not exists summary_id uuid;

update settlement.monthly_process_metric_summary
set summary_id = gen_random_uuid()
where summary_id is null;

alter table settlement.monthly_process_metric_summary
    alter column summary_id set not null;

create unique index if not exists monthly_process_metric_summary_summary_id_uidx
    on settlement.monthly_process_metric_summary (summary_id);

create unique index if not exists monthly_process_metric_summary_id_month_uidx
    on settlement.monthly_process_metric_summary (summary_id, period_start);

create table if not exists settlement.courier_monthly_process_metric (
    courier_metric_id uuid primary key default gen_random_uuid(),
    summary_id uuid not null,
    period_start date not null,
    courier_id text not null,
    courier_name text not null default '',
    courier_month_key text generated always as (
        extract(year from period_start)::integer::text || '-' ||
        lpad(extract(month from period_start)::integer::text, 2, '0') || '-' ||
        courier_id
    ) stored,
    settlement_opened_at timestamptz,
    settlement_accepted_at timestamptz,
    tig_accepted_at timestamptz,
    invoice_uploaded_at timestamptz,
    paid_at timestamptz,
    opening_to_settlement_hours numeric,
    settlement_to_tig_hours numeric,
    tig_to_invoice_hours numeric,
    invoice_to_paid_hours numeric,
    opening_to_paid_hours numeric,
    financial_complaint_count integer not null default 0,
    responded_complaint_count integer not null default 0,
    response_average_hours numeric not null default 0,
    malus_huf numeric not null default 0,
    other_deductions_huf numeric not null default 0,
    deductions_huf numeric not null default 0,
    closure_snapshot jsonb not null default '{}'::jsonb,
    source_updated_at timestamptz,
    calculated_at timestamptz not null default now(),
    calculated_by text not null default 'PWA',
    constraint courier_monthly_process_metric_summary_fk
        foreign key (summary_id, period_start)
        references settlement.monthly_process_metric_summary (summary_id, period_start)
        on delete cascade,
    constraint courier_monthly_process_metric_period_courier_uidx
        unique (period_start, courier_id)
);

create index if not exists courier_monthly_process_metric_month_idx
    on settlement.courier_monthly_process_metric (period_start desc);

create index if not exists courier_monthly_process_metric_courier_idx
    on settlement.courier_monthly_process_metric (courier_id, period_start desc);

grant select, insert, update, delete on settlement.courier_monthly_process_metric to service_role;

notify pgrst, 'reload schema';

commit;
