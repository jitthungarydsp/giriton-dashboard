create table if not exists settlement.mobile_settlement_period_config (
    period_start date primary key,
    calculation_mode text not null check (calculation_mode in ('API', 'Excel')),
    warehouse_label text not null default 'Összes',
    session_id text,
    visibility_mode text not null default 'original'
        check (visibility_mode in ('original', 'settlement_only', 'settlement_and_tig')),
    source_note text,
    updated_by text,
    updated_at timestamptz not null default now()
);

alter table settlement.mobile_settlement_period_config
    add column if not exists visibility_mode text not null default 'original';

alter table settlement.mobile_settlement_period_config
    drop constraint if exists mobile_settlement_period_config_visibility_mode_check;

alter table settlement.mobile_settlement_period_config
    add constraint mobile_settlement_period_config_visibility_mode_check
    check (visibility_mode in ('original', 'settlement_only', 'settlement_and_tig'));

create index if not exists idx_mobile_settlement_period_config_mode
    on settlement.mobile_settlement_period_config (calculation_mode);
