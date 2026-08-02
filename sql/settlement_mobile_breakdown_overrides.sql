create table if not exists settlement.mobile_settlement_breakdown_overrides (
    period_start date not null,
    courier_id text not null,
    item_key text not null,
    item_label text not null,
    amount_value numeric not null default 0,
    amount_kind text not null default 'huf' check (amount_kind in ('huf', 'count')),
    note text,
    updated_by text,
    updated_at timestamptz not null default now(),
    primary key (period_start, courier_id, item_key)
);

create index if not exists idx_mobile_breakdown_overrides_courier_month
    on settlement.mobile_settlement_breakdown_overrides (courier_id, period_start);
