-- dsp_driver_detail_raw takaritas.
--
-- Cel:
-- - hely felszabaditasa a regi, mar nem elo DSP fetch-drivers-detail nyers menteseibol
-- - az aktualis honap vedelme
--
-- Fontos:
-- - Supabase read-only modban a DELETE/DROP nem fog lefutni.
-- - A DROP csak akkor javasolt, ha biztos, hogy a regi DSP detail fallback mar nem kell.

begin;

-- 1) Ellenorzes torles elott.
select
  count(*) as osszes_sor,
  min(work_date) as elso_nap,
  max(work_date) as utolso_nap
from public.dsp_driver_detail_raw;

select
  date_trunc('month', work_date)::date as honap,
  count(*) as sorok
from public.dsp_driver_detail_raw
group by 1
order by 1 desc;

-- 2) Biztonsagos takaritas: csak az aktualis honap elotti sorok mennek.
-- 2026-09-21-en ez 2026-09-01 elotti adatokat jelent.
delete from public.dsp_driver_detail_raw
where work_date < date_trunc('month', current_date)::date;

-- 3) Ellenorzes torles utan.
select
  count(*) as maradt_sor,
  min(work_date) as maradt_elso_nap,
  max(work_date) as maradt_utolso_nap
from public.dsp_driver_detail_raw;

commit;

-- TELJES KUKAZAS, csak ha biztosan nem kell mar a tabla:
-- drop table if exists public.dsp_driver_detail_raw;
