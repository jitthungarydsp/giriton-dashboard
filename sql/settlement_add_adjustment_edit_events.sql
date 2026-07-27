begin;

alter table settlement.courier_settlement_adjustment_event
    drop constraint if exists courier_settlement_adjustment_event_event_type_check;

alter table settlement.courier_settlement_adjustment_event
    add constraint courier_settlement_adjustment_event_event_type_check
    check (event_type in ('created', 'updated', 'deleted', 'reset'));

commit;
