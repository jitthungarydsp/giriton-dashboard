begin;

alter table settlement.courier_settlement_adjustment
    add column if not exists valid_from date,
    add column if not exists valid_to date,
    add column if not exists source_key text;

update settlement.courier_settlement_adjustment
set valid_from = coalesce(valid_from, effective_date, current_date)
where valid_from is null;

create index if not exists courier_settlement_adjustment_validity_idx
    on settlement.courier_settlement_adjustment (courier_id, valid_from, valid_to)
    where deleted_at is null and is_active;

commit;
