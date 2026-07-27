begin;

-- Safe migration for existing settlement parameter tables. It stores the
-- actual JITT Excel header selected for Delay and Compliance rules.
alter table settlement.cfg_jitt_delay_bonus_rules
    add column if not exists excel_source_field text;
alter table settlement.cfg_jitt_compliance_bonus_rules
    add column if not exists excel_source_field text;

commit;
