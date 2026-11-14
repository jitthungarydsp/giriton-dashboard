-- Persisted monthly main indicators for the PWA "Elszámolási folyamat" menu.
-- Run once in the Supabase SQL Editor. The PWA writes one updatable row per month.

begin;

create table if not exists settlement.monthly_process_metric_summary (
    period_start date primary key,
    completed_flow_count integer not null default 0,
    complaint_flow_count integer not null default 0,
    complaint_total integer not null default 0,
    complaints_average numeric not null default 0,
    response_count integer not null default 0,
    response_average_hours numeric not null default 0,
    response_median_hours numeric not null default 0,
    deductions_total_huf numeric not null default 0,
    malus_total_huf numeric not null default 0,
    other_deductions_total_huf numeric not null default 0,
    deductions_average_huf numeric not null default 0,
    opening_to_settlement jsonb not null default '{}'::jsonb,
    settlement_to_tig jsonb not null default '{}'::jsonb,
    tig_to_invoice jsonb not null default '{}'::jsonb,
    invoice_to_paid jsonb not null default '{}'::jsonb,
    opening_to_paid jsonb not null default '{}'::jsonb,
    with_complaint_flow_count integer not null default 0,
    with_complaint_deductions_huf numeric not null default 0,
    with_complaint_deductions_average_huf numeric not null default 0,
    without_complaint_flow_count integer not null default 0,
    without_complaint_deductions_huf numeric not null default 0,
    without_complaint_deductions_average_huf numeric not null default 0,
    source_updated_at timestamptz,
    source_counts jsonb not null default '{}'::jsonb,
    definition_version text not null default '2026-11-14-v1',
    calculated_at timestamptz not null default now(),
    calculated_by text not null default 'PWA'
);

alter table settlement.monthly_process_metric_summary
    add column if not exists opening_to_settlement jsonb not null default '{}'::jsonb,
    add column if not exists settlement_to_tig jsonb not null default '{}'::jsonb,
    add column if not exists tig_to_invoice jsonb not null default '{}'::jsonb,
    add column if not exists invoice_to_paid jsonb not null default '{}'::jsonb,
    add column if not exists opening_to_paid jsonb not null default '{}'::jsonb,
    add column if not exists with_complaint_flow_count integer not null default 0,
    add column if not exists with_complaint_deductions_huf numeric not null default 0,
    add column if not exists with_complaint_deductions_average_huf numeric not null default 0,
    add column if not exists without_complaint_flow_count integer not null default 0,
    add column if not exists without_complaint_deductions_huf numeric not null default 0,
    add column if not exists without_complaint_deductions_average_huf numeric not null default 0;

create index if not exists monthly_process_metric_summary_calculated_at_idx
    on settlement.monthly_process_metric_summary (calculated_at desc);

grant select, insert, update on settlement.monthly_process_metric_summary to service_role;

notify pgrst, 'reload schema';

commit;
