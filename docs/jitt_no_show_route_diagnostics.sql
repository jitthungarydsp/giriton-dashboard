drop view if exists public.vw_jitt_no_show_route_diagnostics_detail;
drop view if exists public.vw_jitt_no_show_fairness_list;
drop view if exists public.vw_jitt_mart_shift_no_show_analysis;
drop view if exists public.vw_jitt_no_show_route_diagnostics;

create or replace view public.vw_jitt_mart_shift_no_show_analysis as
select
    stories.work_date,
    stories.warehouse_name,
    stories.courier_id::text as courier_id,
    stories.courier_name,
    stories.route_id,
    stories.shift_id,
    stories.shift_name,
    stories.shift_start,
    stories.shift_end,
    stories.available_for_shift_since,
    stories.assigned_at,
    stories.planned_departure,
    stories.real_departure,
    stories.planned_return,
    stories.real_return,
    stories.assignment_mode,
    (
        stories.shift_start is not null
        and stories.shift_end is not null
        and stories.available_for_shift_since is not null
        and stories.available_for_shift_since between stories.shift_start and stories.shift_end
    ) as available_in_shift,
    (
        stories.shift_start is not null
        and coalesce(
            stories.real_departure,
            stories.planned_departure,
            stories.assigned_at,
            stories.route_created_at
        ) is not null
        and coalesce(stories.real_return, stories.planned_return) is not null
        and coalesce(
            stories.real_departure,
            stories.planned_departure,
            stories.assigned_at,
            stories.route_created_at
        ) < stories.shift_start
        and coalesce(stories.real_return, stories.planned_return) > stories.shift_start
    ) as route_overlaps_shift_start,
    case
        when stories.shift_start is null or stories.shift_end is null
            then 'NEM DONT HETO / HIANZIK A MUSZAK IDO'
        when stories.available_for_shift_since between stories.shift_start and stories.shift_end
            then 'MEGJELENT / VAN ELERHETO STATUSZ A MUSZAKBAN'
        when coalesce(
                stories.real_departure,
                stories.planned_departure,
                stories.assigned_at,
                stories.route_created_at
             ) < stories.shift_start
             and coalesce(stories.real_return, stories.planned_return) > stories.shift_start
            then 'NEM NO-SHOW / TURAN VOLT A MUSZAK KEZDETEKOR'
        when stories.available_for_shift_since is null
            then 'NO-SHOW GYANU / NINCS ELERHETO STATUSZ'
        else 'NO-SHOW GYANU / ELERHETO STATUSZ NINCS A MUSZAKBAN'
    end as mart_shift_decision,
    stories.story_text,
    stories.updated_at
from public.mart_dsp_route_stories stories;

create or replace view public.vw_jitt_no_show_route_diagnostics as
with no_shows as (
    select
        source_name,
        dsp_code,
        dsp_id,
        warehouse_id,
        warehouse_code,
        work_date,
        courier_id,
        courier_name,
        order_count,
        route_count,
        delayed_order_count,
        pct_of_delayed_orders,
        shift_count,
        late_count,
        did_not_come_count,
        pct_late_evaluation,
        pct_did_not_come_evaluation,
        raw_fetched_at
    from public.raw_jitt_invoice_perf_couriers_daily
    where coalesce(did_not_come_count, 0) > 0
),
route_summary as (
    select
        work_date,
        courier_id::text as courier_id,
        count(*) as mart_route_story_count,
        count(*) filter (where assigned_at is not null) as assigned_route_count,
        count(*) filter (
            where available_for_shift_since between shift_start and shift_end
        ) as checked_in_route_count,
        count(*) filter (where courier_registered_at is not null) as registered_route_count,
        count(*) filter (where real_departure is not null) as departed_route_count,
        count(*) filter (where real_return is not null) as returned_route_count,
        count(*) filter (where assignment_mode ilike '%manual%') as manual_assignment_count,
        count(*) filter (
            where coalesce(real_departure, planned_departure, assigned_at, route_created_at) < shift_start
              and coalesce(real_return, planned_return) > shift_start
        ) as route_overlaps_shift_count,
        min(shift_start) as first_shift_start,
        min(available_for_shift_since) as first_available_for_shift_since,
        min(courier_registered_at) as first_courier_registered_at,
        min(assigned_at) as first_assigned_at,
        max(real_return) as last_real_return,
        max(booking_shift_count) as booking_shift_count,
        string_agg(
            distinct nullif(shift_name, ''),
            ' | '
            order by nullif(shift_name, '')
        ) as shift_names,
        string_agg(
            distinct nullif(assignment_mode, ''),
            ' | '
            order by nullif(assignment_mode, '')
        ) as assignment_modes,
        string_agg(
            left(story_text, 350),
            E'\n---\n'
            order by route_id
        ) as route_story_sample
    from public.mart_dsp_route_stories
    group by work_date, courier_id::text
),
booked_shifts as (
    select
        work_date,
        courier_id::text as courier_id,
        warehouse,
        shift_text,
        booking_code,
        serial,
        (
            work_date
            + substring(shift_text from '([0-9]{1,2}:[0-9]{2})')::time
        ) as booked_shift_start
    from public.raw_muszakpro_bookings
    where courier_id is not null
      and substring(shift_text from '([0-9]{1,2}:[0-9]{2})') is not null
),
shift_overlap_claim as (
    select
        no_shows.work_date,
        no_shows.courier_id,
        count(*) as overlap_route_count,
        string_agg(stories.route_id::text, ', ' order by stories.work_date, stories.route_id) as overlap_route_ids,
        string_agg(
            distinct booked_shifts.shift_text,
            ' | '
            order by booked_shifts.shift_text
        ) as overlap_shift_texts,
        min(booked_shifts.booked_shift_start) as overlap_next_shift_start,
        max(stories.real_return) as overlap_latest_real_return,
        max(stories.planned_return) as overlap_latest_planned_return,
        max(
            extract(
                epoch from (
                    coalesce(stories.real_return, stories.planned_return)
                    - booked_shifts.booked_shift_start
                )
            ) / 60
        )::integer as overlap_delay_minutes,
        string_agg(
            left(stories.story_text, 350),
            E'\n---\n'
            order by stories.work_date, stories.route_id
        ) as overlap_story_sample
    from no_shows
    join booked_shifts
        on booked_shifts.work_date = no_shows.work_date
       and booked_shifts.courier_id = no_shows.courier_id
    join public.mart_dsp_route_stories stories
        on stories.courier_id::text = no_shows.courier_id
       and stories.work_date between no_shows.work_date - 1 and no_shows.work_date
       and coalesce(stories.real_departure, stories.planned_departure, stories.assigned_at, stories.shift_start)
           < booked_shifts.booked_shift_start
       and coalesce(stories.real_return, stories.planned_return) > booked_shifts.booked_shift_start
    group by no_shows.work_date, no_shows.courier_id
)
select
    no_shows.work_date,
    no_shows.warehouse_code,
    no_shows.courier_id,
    no_shows.courier_name,
    no_shows.did_not_come_count,
    no_shows.pct_did_not_come_evaluation,
    no_shows.shift_count,
    no_shows.route_count,
    no_shows.order_count,
    no_shows.late_count,
    no_shows.delayed_order_count,
    no_shows.pct_late_evaluation,
    no_shows.pct_of_delayed_orders,
    coalesce(route_summary.mart_route_story_count, 0) as mart_route_story_count,
    coalesce(route_summary.assigned_route_count, 0) as assigned_route_count,
    coalesce(route_summary.checked_in_route_count, 0) as checked_in_route_count,
    coalesce(route_summary.registered_route_count, 0) as registered_route_count,
    coalesce(route_summary.departed_route_count, 0) as departed_route_count,
    coalesce(route_summary.returned_route_count, 0) as returned_route_count,
    coalesce(route_summary.manual_assignment_count, 0) as manual_assignment_count,
    coalesce(route_summary.route_overlaps_shift_count, 0) as route_overlaps_shift_count,
    route_summary.first_shift_start,
    route_summary.first_available_for_shift_since,
    route_summary.first_courier_registered_at,
    route_summary.first_assigned_at,
    route_summary.last_real_return,
    route_summary.booking_shift_count,
    route_summary.shift_names,
    route_summary.assignment_modes,
    coalesce(shift_overlap_claim.overlap_route_count, 0) as overlap_route_count,
    shift_overlap_claim.overlap_route_ids,
    shift_overlap_claim.overlap_shift_texts,
    shift_overlap_claim.overlap_next_shift_start,
    shift_overlap_claim.overlap_latest_real_return,
    shift_overlap_claim.overlap_latest_planned_return,
    shift_overlap_claim.overlap_delay_minutes,
    (shift_overlap_claim.overlap_route_count is not null) as is_reklamacio_candidate,
    case
        when shift_overlap_claim.overlap_route_count is not null
            then 'REKLAMACIO_GYANU: az elozo tura visszaerkezese belenyult a kovetkezo foglalt muszak kezdetebe.'
        when route_summary.mart_route_story_count is null
            then 'Nincs mart route story erre a futarra ezen a napon: valoszinuleg nem volt DSP attendance/route adat.'
        when route_summary.route_overlaps_shift_count > 0
            then 'NEM NO-SHOW: a futar turan volt a muszak kezdete/idablaka alatt.'
        when route_summary.checked_in_route_count = 0
             and route_summary.assigned_route_count > 0
            then 'Kapott turat, de nincs available_for_shift_since: manualis kiosztas vagy nem latszo sorba allas.'
        when route_summary.checked_in_route_count = 0
             and route_summary.registered_route_count = 0
            then 'Nem latszik bejelentkezes/regisztracio a mart adatokban.'
        when route_summary.assigned_route_count = 0
            then 'Van mart sor, de nincs kiosztott tura: muszakban lehetett, de nem kapott route-ot.'
        when route_summary.departed_route_count = 0
            then 'Volt kiosztas, de nincs valos indulas: tura elindulasa hianyzik vagy torlodott.'
        else 'Volt mart route tortenet is: a no-show oka a route story reszletekbol ellenorizendo.'
    end as likely_reason,
    shift_overlap_claim.overlap_story_sample,
    route_summary.route_story_sample,
    no_shows.raw_fetched_at
from no_shows
left join route_summary
    on route_summary.work_date = no_shows.work_date
   and route_summary.courier_id = no_shows.courier_id
left join shift_overlap_claim
    on shift_overlap_claim.work_date = no_shows.work_date
   and shift_overlap_claim.courier_id = no_shows.courier_id;

create or replace view public.vw_jitt_no_show_route_diagnostics_detail as
select
    no_shows.work_date,
    no_shows.warehouse_code,
    no_shows.courier_id,
    no_shows.courier_name,
    no_shows.did_not_come_count,
    case
        when stories.next_booking_shift_start is not null
             and stories.next_booking_shift_start::date = no_shows.work_date
             and coalesce(stories.real_return, stories.planned_return) > stories.next_booking_shift_start
            then 'previous_route_overlaps_missing_shift'
        when stories.work_date = no_shows.work_date
            then 'same_day_route_story'
        else 'no_route_story'
    end as story_relation,
    (
        stories.next_booking_shift_start is not null
        and stories.next_booking_shift_start::date = no_shows.work_date
        and coalesce(stories.real_return, stories.planned_return) > stories.next_booking_shift_start
    ) as is_reklamacio_candidate,
    stories.route_id,
    stories.work_date as story_work_date,
    stories.shift_id,
    stories.shift_name,
    stories.shift_start,
    stories.shift_end,
    stories.available_for_shift_since,
    stories.courier_registered_at,
    stories.assigned_at,
    stories.planned_departure,
    stories.real_departure,
    stories.planned_return,
    stories.real_return,
    stories.assignment_mode,
    stories.booking_shift_count,
    stories.next_booking_shift_text,
    stories.next_booking_shift_start,
    stories.next_shift_delay_minutes,
    stories.story_text
from public.raw_jitt_invoice_perf_couriers_daily no_shows
left join public.mart_dsp_route_stories stories
    on stories.courier_id::text = no_shows.courier_id
   and (
        stories.work_date = no_shows.work_date
        or stories.next_booking_shift_start::date = no_shows.work_date
   )
where coalesce(no_shows.did_not_come_count, 0) > 0;

create or replace view public.vw_jitt_no_show_fairness_list as
select
    diagnostics.courier_id,
    diagnostics.courier_name,
    diagnostics.work_date,
    diagnostics.warehouse_code,
    diagnostics.did_not_come_count as kifli_no_show_count,
    diagnostics.shift_count,
    diagnostics.route_count,
    diagnostics.order_count,
    diagnostics.is_reklamacio_candidate,
    case
        when diagnostics.route_overlaps_shift_count > 0
            then 'NEM NO-SHOW / TURAN VOLT A MUSZAK KEZDETEKOR'
        when diagnostics.is_reklamacio_candidate
            then 'NEM JOGOS / REKLAMACIO GYANU'
        when diagnostics.mart_route_story_count = 0
            then 'NEM DONT HETO / NINCS MART ADAT'
        when diagnostics.checked_in_route_count = 0
             and diagnostics.assigned_route_count = 0
            then 'VALOSZINULEG JOGOS'
        when diagnostics.checked_in_route_count = 0
             and diagnostics.assigned_route_count > 0
            then 'NEM DONT HETO / MANUALIS VAGY HIANYOS SORBA ALLAS'
        when diagnostics.departed_route_count = 0
             and diagnostics.assigned_route_count > 0
            then 'NEM DONT HETO / VOLT KIOSZTAS, NINCS INDULAS'
        else 'JOGOSNAK LATSZIK / NINCS ELOZO TURA OVERLAP'
    end as our_decision,
    diagnostics.likely_reason,
    diagnostics.overlap_route_ids,
    diagnostics.overlap_shift_texts,
    diagnostics.overlap_next_shift_start,
    diagnostics.overlap_latest_real_return,
    diagnostics.overlap_latest_planned_return,
    diagnostics.overlap_delay_minutes,
    diagnostics.mart_route_story_count,
    diagnostics.assigned_route_count,
    diagnostics.checked_in_route_count,
    diagnostics.route_overlaps_shift_count,
    diagnostics.registered_route_count,
    diagnostics.departed_route_count,
    diagnostics.returned_route_count,
    diagnostics.first_shift_start,
    diagnostics.first_available_for_shift_since,
    diagnostics.first_courier_registered_at,
    diagnostics.first_assigned_at,
    diagnostics.last_real_return,
    diagnostics.shift_names,
    diagnostics.assignment_modes
from public.vw_jitt_no_show_route_diagnostics diagnostics;

comment on view public.vw_jitt_no_show_route_diagnostics is
    'JITT didNotCome/no-show napi futar diagnosztika mart_dsp_route_stories osszekapcsolassal.';

comment on view public.vw_jitt_no_show_route_diagnostics_detail is
    'JITT didNotCome/no-show route reszletes diagnosztika mart_dsp_route_stories alapjan.';

comment on view public.vw_jitt_no_show_fairness_list is
    'Kifli szerinti JITT no-show napok futaronkent, sajat jogossagi/reklamacios besorolassal.';

comment on view public.vw_jitt_mart_shift_no_show_analysis is
    'Mart alapu JITT muszak megjelenes/no-show elemzes: elerheto statusz muszakon belul, route overlap mentessel.';
