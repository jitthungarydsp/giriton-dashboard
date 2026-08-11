-- Juliusi elso muszak bejelentkezes + no-show audit.
--
-- Cel:
-- 1) Megmutatja, hogy 2026 juliusban futaronkent/naponkent az elso muszakra
--    mikor jelentkezett be a kollega.
-- 2) Osszeveti a sajat muszakszintu minosegi tablankat
--    (public.dsp_courier_shift_quality_report) a napi Kifli/JITT API no-show
--    adattal (public.raw_jitt_invoice_perf_couriers_daily).
--
-- Futtatas Supabase SQL Editorban.
-- Letrehoz egy nezeti kimutatast:
--   public.vw_july_first_shift_login_no_show_audit

create or replace view public.vw_july_first_shift_login_no_show_audit as

with quality_shifts as (
    select
        q.*,
        row_number() over (
            partition by q.work_date, q.courier_id
            order by
                q.first_shift_of_day desc,
                q.shift_start_at nulls last,
                q.shift_key
        ) as day_shift_rank,
        count(*) filter (where q.no_show) over (
            partition by q.work_date, q.courier_id
        ) as our_no_show_shift_count,
        count(*) over (
            partition by q.work_date, q.courier_id
        ) as our_shift_count
    from public.dsp_courier_shift_quality_report q
    where q.work_date >= date '2026-07-01'
      and q.work_date < date '2026-08-01'
),
first_shift as (
    select
        *
    from quality_shifts
    where day_shift_rank = 1
),
api_daily as (
    select
        p.work_date,
        p.courier_id::integer as courier_id,
        max(p.courier_name) as courier_name,
        sum(coalesce(p.shift_count, 0)) as api_shift_count,
        sum(coalesce(p.late_count, 0)) as api_late_count,
        sum(coalesce(p.did_not_come_count, 0)) as api_no_show_count,
        sum(coalesce(p.order_count, 0)) as api_order_count,
        sum(coalesce(p.route_count, 0)) as api_route_count,
        sum(coalesce(p.delayed_order_count, 0)) as api_delayed_order_count,
        max(p.raw_fetched_at) as api_fetched_at
    from public.raw_jitt_invoice_perf_couriers_daily p
    where p.work_date >= date '2026-07-01'
      and p.work_date < date '2026-08-01'
    group by p.work_date, p.courier_id::integer
),
daily_audit as (
    select
        fs.work_date,
        fs.courier_id,
        coalesce(fs.courier_name, api.courier_name) as courier_name,
        fs.warehouse,
        fs.shift_name as first_shift_name,
        fs.shift_start_at as first_shift_start_at,
        fs.shift_end_at as first_shift_end_at,
        fs.available_at as first_shift_available_at,
        fs.queue_started_at as first_shift_queue_started_at,
        round(extract(epoch from (fs.available_at - fs.shift_start_at)) / 60.0)::integer
            as available_vs_shift_start_minutes,
        round(extract(epoch from (fs.queue_started_at - fs.shift_start_at)) / 60.0)::integer
            as queue_vs_shift_start_minutes,
        fs.queued_on_time,
        fs.no_show as first_shift_no_show,
        fs.no_show_reason as first_shift_no_show_reason,
        fs.our_shift_count,
        fs.our_no_show_shift_count,
        coalesce(api.api_shift_count, 0) as api_shift_count,
        coalesce(api.api_late_count, 0) as api_late_count,
        coalesce(api.api_no_show_count, 0) as api_no_show_count,
        coalesce(api.api_order_count, 0) as api_order_count,
        coalesce(api.api_route_count, 0) as api_route_count,
        coalesce(api.api_delayed_order_count, 0) as api_delayed_order_count,
        fs.route_id,
        fs.route_count,
        fs.assignment_mode,
        fs.address_count,
        fs.time_window_late_count,
        fs.planned_departure_at,
        fs.planned_return_at,
        fs.real_departure_at,
        fs.real_return_at,
        fs.late_order_cutoff_exception,
        fs.quality_ok,
        case
            when fs.available_at is null and fs.queue_started_at is null then 'Nincs bejelentkezesi adat'
            when coalesce(fs.queue_started_at, fs.available_at) <= fs.shift_start_at then 'Idoben bejelentkezett'
            else 'Keso bejelentkezes'
        end as first_shift_login_status,
        case
            when coalesce(api.api_no_show_count, 0) = 0 and coalesce(fs.our_no_show_shift_count, 0) = 0
                then 'OK - nincs no-show'
            when coalesce(api.api_no_show_count, 0) > 0 and coalesce(fs.our_no_show_shift_count, 0) > 0
                then 'Egyezik - API es sajat no-show is van'
            when coalesce(api.api_no_show_count, 0) > 0 and coalesce(fs.our_no_show_shift_count, 0) = 0
                then 'Ellenorizendo - API no-show, sajat szamitas szerint nem'
            when coalesce(api.api_no_show_count, 0) = 0 and coalesce(fs.our_no_show_shift_count, 0) > 0
                then 'Ellenorizendo - sajat no-show, API szerint nem'
            else 'Ellenorizendo'
        end as no_show_audit_status,
        api.api_fetched_at,
        fs.updated_at as quality_updated_at
    from first_shift fs
    left join api_daily api
        on api.work_date = fs.work_date
       and api.courier_id = fs.courier_id
)
select
    work_date as datum,
    courier_id as futar_id,
    courier_name as futar_nev,
    warehouse as raktar,
    first_shift_name as elso_muszak,
    first_shift_start_at as elso_muszak_kezdete,
    first_shift_available_at as elerheto_volt,
    first_shift_queue_started_at as sorba_allt,
    available_vs_shift_start_minutes as elerheto_elteres_perc,
    queue_vs_shift_start_minutes as sorba_allas_elteres_perc,
    first_shift_login_status as bejelentkezesi_statusz,
    first_shift_no_show as elso_muszak_sajat_no_show,
    first_shift_no_show_reason as sajat_no_show_ok,
    our_no_show_shift_count as sajat_no_show_db_napon,
    api_no_show_count as api_no_show_db_napon,
    no_show_audit_status as no_show_ellenorzes,
    route_id,
    route_count as muszakhoz_tura_db,
    assignment_mode as kiosztas_modja,
    address_count as cim_db,
    time_window_late_count as idokapun_tuli_cim_db,
    planned_departure_at as tervezett_indulas,
    planned_return_at as tervezett_visszaerkezes,
    real_departure_at as valos_indulas,
    real_return_at as valos_visszaerkezes,
    late_order_cutoff_exception as zarasi_kivetel,
    quality_ok as sajat_quality_ok,
    api_shift_count,
    api_late_count,
    api_order_count,
    api_route_count,
    api_delayed_order_count,
    api_fetched_at,
    quality_updated_at
from daily_audit
;

-- 1) Reszletes napi kimutatas.
select *
from public.vw_july_first_shift_login_no_show_audit
order by datum, futar_nev nulls last, futar_id;

-- 2) Futaronkenti juliusi osszesito.
select
    futar_id,
    max(futar_nev) as futar_nev,
    count(*) as nap_db,
    count(*) filter (where bejelentkezesi_statusz = 'Idoben bejelentkezett') as idoben_elso_muszak_db,
    count(*) filter (where bejelentkezesi_statusz = 'Keso bejelentkezes') as keso_elso_muszak_db,
    count(*) filter (where bejelentkezesi_statusz = 'Nincs bejelentkezesi adat') as nincs_bejelentkezes_db,
    sum(sajat_no_show_db_napon) as sajat_no_show_db,
    sum(api_no_show_db_napon) as api_no_show_db,
    count(*) filter (where no_show_ellenorzes like 'Ellenorizendo%') as ellenorizendo_nap_db,
    round(avg(sorba_allas_elteres_perc) filter (where sorba_allas_elteres_perc is not null), 1)
        as atlag_sorba_allas_elteres_perc,
    min(sorba_allt) as elso_rogzitett_sorba_allas,
    max(quality_updated_at) as utolso_quality_frissites
from public.vw_july_first_shift_login_no_show_audit
group by futar_id
order by ellenorizendo_nap_db desc, keso_elso_muszak_db desc, futar_nev;
