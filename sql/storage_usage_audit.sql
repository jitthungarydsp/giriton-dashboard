-- Run in the Supabase SQL Editor with a database role that can read pg_catalog.
-- This is read-only: it does not change tables or delete files.

-- 1) Actual table size, including indexes and TOAST storage.
select
  schemaname,
  relname as table_name,
  pg_total_relation_size(relid) as total_bytes,
  pg_size_pretty(pg_total_relation_size(relid)) as total_size,
  pg_size_pretty(pg_table_size(relid)) as table_and_toast_size,
  pg_size_pretty(pg_indexes_size(relid)) as indexes_size,
  n_live_tup as estimated_live_rows
from pg_catalog.pg_statio_user_tables
order by pg_total_relation_size(relid) desc;

-- 2) Tables that currently store uploaded binary content in Base64 text.
-- The Base64 column is normally about 1.33x the original file size.
select *
from (
  select
    'public.pwa_atm_payment' as table_name,
    count(*) as row_count,
    coalesce(sum(file_size), 0)::bigint as original_file_bytes,
    coalesce(sum(pg_column_size(file_content_base64)), 0)::bigint as stored_base64_bytes,
    pg_size_pretty(coalesce(sum(file_size), 0)::bigint) as original_file_size,
    pg_size_pretty(coalesce(sum(pg_column_size(file_content_base64)), 0)::bigint) as stored_base64_size
  from public.pwa_atm_payment

  union all

  select
    'public.pwa_device_condition_photos',
    count(*),
    coalesce(sum(file_size), 0)::bigint,
    coalesce(sum(pg_column_size(file_content_base64)), 0)::bigint,
    pg_size_pretty(coalesce(sum(file_size), 0)::bigint),
    pg_size_pretty(coalesce(sum(pg_column_size(file_content_base64)), 0)::bigint)
  from public.pwa_device_condition_photos

  union all

  select
    'public.courier_route_alert_photos',
    count(*),
    coalesce(sum(file_size), 0)::bigint,
    coalesce(sum(pg_column_size(file_content_base64)), 0)::bigint,
    pg_size_pretty(coalesce(sum(file_size), 0)::bigint),
    pg_size_pretty(coalesce(sum(pg_column_size(file_content_base64)), 0)::bigint)
  from public.courier_route_alert_photos

  union all

  select
    'public.peopleforce_documents',
    count(*),
    coalesce(sum(file_size), 0)::bigint,
    coalesce(sum(pg_column_size(file_content_base64)), 0)::bigint,
    pg_size_pretty(coalesce(sum(file_size), 0)::bigint),
    pg_size_pretty(coalesce(sum(pg_column_size(file_content_base64)), 0)::bigint)
  from public.peopleforce_documents
) content_usage
order by stored_base64_bytes desc;

-- 3) Vehicle versus phone photos in the shared photo table.
select
  coalesce(r.device_type, 'unknown') as device_type,
  count(p.id) as photo_count,
  coalesce(sum(p.file_size), 0)::bigint as original_file_bytes,
  pg_size_pretty(coalesce(sum(p.file_size), 0)::bigint) as original_file_size,
  coalesce(sum(pg_column_size(p.file_content_base64)), 0)::bigint as stored_base64_bytes,
  pg_size_pretty(coalesce(sum(pg_column_size(p.file_content_base64)), 0)::bigint) as stored_base64_size
from public.pwa_device_condition_photos p
join public.pwa_device_condition_reports r on r.id = p.report_id
group by r.device_type
order by stored_base64_bytes desc;

-- 4) Largest individual uploads, useful before moving to object storage.
select
  'pwa_device_condition_photos' as source_table,
  id::text as file_id,
  file_name,
  mime_type,
  file_size,
  pg_size_pretty(file_size::bigint) as file_size_pretty,
  uploaded_at
from public.pwa_device_condition_photos
order by file_size desc nulls last
limit 50;
