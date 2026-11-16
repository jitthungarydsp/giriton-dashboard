-- Javított elszámolási folyamatmutatókhoz szükséges séma-kiegészítés.
-- Supabase SQL Editorben egyszer futtasd le, mielőtt a havi adatokat újraépíted.

begin;

create extension if not exists pgcrypto;

-- A korábbi telepítés kitöltötte a meglévő sorok azonosítóját, de új hónap
-- létrehozásakor nem generált automatikusan azonosítót.
alter table settlement.monthly_process_metric_summary
    alter column summary_id set default gen_random_uuid();

grant select, insert, update, delete on settlement.monthly_process_metric_summary to service_role;
grant select, insert, update, delete on settlement.courier_monthly_process_metric to service_role;

notify pgrst, 'reload schema';

commit;
