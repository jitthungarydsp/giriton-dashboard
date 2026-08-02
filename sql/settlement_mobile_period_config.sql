create table if not exists settlement.mobile_settlement_period_config (
    period_start date primary key,
    calculation_mode text not null check (calculation_mode in ('API', 'Excel')),
    warehouse_label text not null default 'Összes',
    session_id text,
    source_note text,
    updated_by text,
    updated_at timestamptz not null default now()
);

create index if not exists idx_mobile_settlement_period_config_mode
    on settlement.mobile_settlement_period_config (calculation_mode);
