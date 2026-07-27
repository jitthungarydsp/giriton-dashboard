begin;

alter table settlement.courier_settlement_adjustment
    alter column session_id drop not null;

alter table settlement.courier_settlement_adjustment_event
    alter column session_id drop not null;

commit;
