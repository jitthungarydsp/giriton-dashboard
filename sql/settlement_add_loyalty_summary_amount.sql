-- Additive migration for loyalty-only recalculation. Run once in SQL Editor.
begin;

alter table settlement.courier_settlement_summary
    add column if not exists loyalty_bonus_huf numeric not null default 0;

notify pgrst, 'reload schema';

commit;
