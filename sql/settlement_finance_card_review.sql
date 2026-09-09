create table if not exists settlement.courier_finance_card_review (
    id bigserial primary key,
    period_start date not null,
    courier_id text not null,
    courier_name text,
    session_id text not null default '',
    calculation_mode text,
    item_key text not null,
    item_label text,
    is_checked boolean not null default false,
    updated_by text,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint courier_finance_card_review_unique
        unique (period_start, courier_id, session_id, item_key)
);

create index if not exists courier_finance_card_review_period_idx
    on settlement.courier_finance_card_review (period_start, courier_id);

grant select, insert, update, delete on settlement.courier_finance_card_review to service_role;
grant usage, select on sequence settlement.courier_finance_card_review_id_seq to service_role;
