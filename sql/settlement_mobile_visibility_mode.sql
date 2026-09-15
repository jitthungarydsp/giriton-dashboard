/*
PWA havi elszámolás/TIG láthatósági főkapcsoló.

Supabase SQL Editorban futtasd egyszer.

visibility_mode:
- original: eredeti folyamat, TIG csak elszámolás elfogadása után aktív
- settlement_only: csak az elszámolás látszik, TIG rejtve marad
- settlement_and_tig: elszámolás és TIG is látszik
*/

alter table settlement.mobile_settlement_period_config
    add column if not exists visibility_mode text not null default 'original';

alter table settlement.mobile_settlement_period_config
    drop constraint if exists mobile_settlement_period_config_visibility_mode_check;

alter table settlement.mobile_settlement_period_config
    add constraint mobile_settlement_period_config_visibility_mode_check
    check (visibility_mode in ('original', 'settlement_only', 'settlement_and_tig'));

update settlement.mobile_settlement_period_config
set visibility_mode = 'original'
where visibility_mode is null
   or visibility_mode not in ('original', 'settlement_only', 'settlement_and_tig');
