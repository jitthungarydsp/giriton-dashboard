/*
Supabase SQL Editorban futtasd.

Ez csak azt listázza, hogy az adott hónapban milyen JIT import sessionök vannak.
Ha ez sem ad sort, akkor a havi JIT Excel sorok nem kerültek be a settlement.jit_row táblába,
vagy a dátum más mezőnéven érkezik a normalized_data JSON-ben.
*/

with params as (
    select date '2026-09-01' as v_period_start
),
period as (
    select
        v_period_start,
        (v_period_start + interval '1 month - 1 day')::date as v_period_end
    from params
),
raw as (
    select
        j.id,
        j.session_id,
        j.source_sheet,
        j.created_at,
        coalesce(
            j.route_date,
            case
                when date_value.date_text ~ '^\d{4}-\d{2}-\d{2}' then left(date_value.date_text, 10)::date
                when date_value.date_text ~ '^\d{4}/\d{2}/\d{2}' then to_date(left(date_value.date_text, 10), 'YYYY/MM/DD')
                when date_value.date_text ~ '^\d{1,2}[./-]\d{1,2}[./-]\d{4}$' then to_date(replace(replace(date_value.date_text, '.', '/'), '-', '/'), 'DD/MM/YYYY')
                when date_value.date_text ~ '^\d+(\.0+)?$' then date '1899-12-30' + date_value.date_text::numeric::integer
            end
        ) as work_date,
        coalesce(nullif(j.normalized_data ->> 'Driver', ''), nullif(j.normalized_data ->> 'driver_name', ''), 'Ismeretlen futár') as driver_name,
        coalesce(nullif(j.normalized_data ->> 'Route Type', ''), nullif(j.normalized_data ->> 'route_type', ''), '-') as route_type,
        coalesce(nullif(j.normalized_data ->> 'Date', ''), nullif(j.normalized_data ->> 'date', ''), nullif(j.normalized_data ->> 'Dátum', ''), nullif(j.normalized_data ->> 'Datum', ''), nullif(j.normalized_data ->> 'work_date', ''), '-') as raw_date_value
    from settlement.jit_row j
    cross join lateral (
        select coalesce(
            nullif(j.normalized_data ->> 'Date', ''),
            nullif(j.normalized_data ->> 'date', ''),
            nullif(j.normalized_data ->> 'Dátum', ''),
            nullif(j.normalized_data ->> 'Datum', ''),
            nullif(j.normalized_data ->> 'work_date', ''),
            ''
        ) as date_text
    ) date_value
)
select
    session_id,
    min(created_at) as first_imported_at,
    max(created_at) as last_imported_at,
    min(work_date) as first_work_date,
    max(work_date) as last_work_date,
    count(*) as rows_total,
    count(*) filter (where lower(route_type) like '%express%') as express_rows,
    count(*) filter (where coalesce(source_sheet, '') ilike 'API financial overview%') as api_financial_rows,
    string_agg(distinct source_sheet, ' | ' order by source_sheet) as source_sheets,
    max(driver_name) as sample_driver,
    max(raw_date_value) as sample_raw_date
from raw
join period p on raw.work_date between p.v_period_start and p.v_period_end
group by session_id
order by last_imported_at desc nulls last, rows_total desc
limit 20;
