begin;

alter table settlement.courier_settlement_adjustment_event
    add column if not exists valid_from date,
    add column if not exists valid_to date;

create index if not exists courier_settlement_adjustment_event_validity_idx
    on settlement.courier_settlement_adjustment_event (courier_id, valid_from, valid_to, created_at desc);

commit;
