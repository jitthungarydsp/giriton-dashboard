-- Dynamic shift rescue suggestions.
-- Minden futas uj collection_id-val ir sort. A latest view mindig a legfrissebb futast mutatja.

create table if not exists public.ops_shift_rescue_suggestions (
    id uuid primary key default gen_random_uuid(),
    collection_id uuid not null,
    work_date date not null,
    warehouse text,
    problem_courier_id integer not null,
    problem_courier_name text,
    problem_route_id text,
    problem_route_assigned_at timestamptz,
    problem_expected_return_at timestamptz,
    problem_current_shift_id text,
    problem_current_shift_name text,
    problem_current_shift_start timestamptz,
    problem_current_shift_end timestamptz,
    problem_target_shift_id text,
    problem_target_shift_name text,
    problem_target_shift_start timestamptz,
    problem_target_shift_end timestamptz,
    delay_minutes integer,
    replacement_courier_id integer,
    replacement_courier_name text,
    replacement_current_route_id text,
    replacement_expected_return_at timestamptz,
    replacement_available_from timestamptz,
    replacement_available_until timestamptz,
    free_gap_minutes integer,
    replacement_reason text,
    score integer not null default 0,
    status text not null default 'new',
    source_summary jsonb not null default '{}'::jsonb,
    collected_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create index if not exists idx_ops_shift_rescue_collection
    on public.ops_shift_rescue_suggestions (collection_id);

create index if not exists idx_ops_shift_rescue_work_date
    on public.ops_shift_rescue_suggestions (work_date);

create index if not exists idx_ops_shift_rescue_problem
    on public.ops_shift_rescue_suggestions (problem_courier_id, work_date);

create index if not exists idx_ops_shift_rescue_replacement
    on public.ops_shift_rescue_suggestions (replacement_courier_id, work_date);


create or replace view public.vw_shift_rescue_latest_suggestions as
with latest as (
    select
        work_date,
        max(collected_at) as collected_at
    from public.ops_shift_rescue_suggestions
    group by work_date
)
select s.*
from public.ops_shift_rescue_suggestions s
join latest l
  on l.work_date = s.work_date
 and l.collected_at = s.collected_at
order by s.work_date, s.problem_target_shift_start, s.score desc;


-- Ellenorzes:
-- select *
-- from public.vw_shift_rescue_latest_suggestions
-- order by work_date, problem_target_shift_start, score desc;
