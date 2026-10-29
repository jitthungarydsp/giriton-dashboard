begin;
create table if not exists public.pwa_quality_complaints (
    id uuid primary key default gen_random_uuid(),
    request_id uuid not null unique,
    courier_id text not null,
    courier_name text not null,
    topic text not null check (topic in ('lateShift', 'uncleanedTimeWindowLate', 'cleanedTimeWindowLate', 'noShow')),
    work_month date not null,
    message text not null check (length(btrim(message)) between 5 and 5000),
    affected_items jsonb not null check (jsonb_typeof(affected_items) = 'array' and jsonb_array_length(affected_items) between 1 and 200),
    status text not null default 'new' check (status in ('new', 'in_review', 'resolved', 'rejected')),
    created_by text not null,
    created_at timestamptz not null default now()
);
create index if not exists pwa_quality_complaints_courier_month_idx
    on public.pwa_quality_complaints (courier_id, work_month, created_at desc);
alter table public.pwa_quality_complaints enable row level security;
revoke all on public.pwa_quality_complaints from anon, authenticated;
grant select, insert, update on public.pwa_quality_complaints to service_role;
notify pgrst, 'reload schema';
commit;
