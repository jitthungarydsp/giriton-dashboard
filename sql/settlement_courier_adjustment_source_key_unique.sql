begin;

create unique index if not exists courier_settlement_adjustment_source_key_uidx
    on settlement.courier_settlement_adjustment (source_key)
    where source_key is not null and deleted_at is null;

notify pgrst, 'reload schema';

commit;
