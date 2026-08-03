begin;

alter table settlement.cfg_jitt_reserve_insurance_rules
    add column if not exists reserve_target_huf integer not null default 50000
        check (reserve_target_huf >= 0);

update settlement.cfg_jitt_reserve_insurance_rules
set reserve_target_huf = 50000
where reserve_target_huf is null or reserve_target_huf = 0;

notify pgrst, 'reload schema';

commit;
