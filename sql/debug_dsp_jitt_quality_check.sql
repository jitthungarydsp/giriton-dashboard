-- DSP/JITT quality ellenorzes
-- Futtasd Supabase SQL Editorban a matrix es az osszesitok gyors ellenorzesehez.

-- 1) Matrix sorok: express + city aktiv, regional bent van, de inaktiv.
select
    metric_type,
    route_type,
    route_type_label,
    is_active,
    count(*) as rows_count,
    min(priority) as first_priority,
    max(priority) as last_priority
from public.dsp_jitt_quality_bonus_matrix
where source = 'jitt_contract_2026_matrix'
group by metric_type, route_type, route_type_label, is_active
order by metric_type, route_type, is_active desc;

-- 2) A teljes matrix emberi olvasasra.
select
    metric_type,
    level_label as vallalkozo_szint,
    courier_level_label as futar_szint,
    case
        when threshold_min is null then '<= ' || threshold_max::text || '%'
        when threshold_max is null then '>= ' || threshold_min::text || '%'
        else threshold_min::text || '% - ' || threshold_max::text || '%'
    end as szazalek_sav,
    duration_label,
    route_type_label,
    is_active,
    company_amount_huf as vallalkozo_osszeg,
    courier_amount_huf as futar_osszeg
from public.dsp_jitt_quality_bonus_matrix
where source = 'jitt_contract_2026_matrix'
order by metric_type, level_code, duration_min_hours nulls first, duration_max_hours;

-- 3) Mart route story route tipus kontroll.
-- Varakozas: route_type = normal, ha van 15 vagy 60 perces idoablak; kulonben express.
select
    work_date,
    route_type,
    count(*) as route_count,
    sum(address_count) as address_count,
    sum(time_window_late_count) as delayed_order_count
from public.mart_dsp_route_stories
where work_date between date '2026-07-01' and date '2026-08-08'
group by work_date, route_type
order by work_date desc, route_type;

-- 4) Egy futar napi quality riportja. Itt csereld a courier_id-t, ha kell.
select
    work_date,
    courier_id,
    courier_name,
    shift_count,
    route_count,
    order_count,
    delayed_order_count,
    delay_percent,
    late_percent,
    no_show_percent,
    route_quality_bad_percent,
    compliance_score_percent,
    company_delay_bonus_huf,
    courier_delay_bonus_huf,
    company_compliance_bonus_huf,
    courier_compliance_bonus_huf,
    company_quality_bonus_total_huf,
    courier_quality_bonus_total_huf,
    delay_level,
    route_quality_level,
    updated_at
from public.dsp_courier_quality_daily
where courier_id = 7644
  and work_date between date '2026-07-01' and date '2026-08-08'
order by work_date desc;

-- 5) Havi osszesito futaronkent, a JITT szamitas alapja.
select
    period_month,
    courier_id,
    courier_name,
    shift_count,
    route_count,
    order_count,
    delayed_order_count,
    delay_percent,
    route_quality_bad_percent as turameg_nem_megfeleles_percent,
    compliance_score_percent,
    company_delay_bonus_huf,
    company_compliance_bonus_huf,
    company_quality_bonus_total_huf,
    courier_delay_bonus_huf,
    courier_compliance_bonus_huf,
    courier_quality_bonus_total_huf,
    updated_at
from public.dsp_courier_quality_monthly
where period_month = date '2026-08-01'
order by courier_quality_bonus_total_huf desc, courier_name;

-- 6) Shift szintu audit: itt latszik, hogy egy muszakhoz milyen route_type es no-show/keses jel tartozik.
select
    work_date,
    courier_id,
    courier_name,
    shift_name,
    route_type,
    shift_start_at,
    shift_end_at,
    route_count,
    address_count,
    time_window_late_count,
    queued_on_time,
    no_show,
    no_show_reason,
    quality_ok,
    source
from public.dsp_courier_shift_quality_report
where courier_id = 7644
  and work_date between date '2026-07-01' and date '2026-08-08'
order by work_date desc, shift_start_at;

-- 7) Gyors ellenorzes: van-e olyan aktiv regional matrix sor, ami veletlenul szamolna?
select *
from public.dsp_jitt_quality_bonus_matrix
where source = 'jitt_contract_2026_matrix'
  and route_type = 'regional'
  and is_active = true;
