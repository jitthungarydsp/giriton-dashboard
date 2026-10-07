create table if not exists public.external_shift_deletion_requests (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'kulso_torles_log_sheet',
    source_sheet_id text not null,
    source_gid integer not null,
    source_row integer not null,
    source_key text not null,
    requested_at_text text,
    work_date date not null,
    shift_text text not null,
    shift_start time,
    email text not null,
    warehouse text not null,
    sheet_status text,
    deletion_status text not null default 'pending',
    hub_booking_id uuid,
    hub_courier_id integer,
    hub_courier_name text,
    hub_shift_template_id integer,
    hub_slot_from time,
    hub_block_key text,
    message text,
    hub_response jsonb not null default '{}'::jsonb,
    processed_at timestamptz,
    sheet_written_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    constraint external_shift_deletion_requests_source_key_unique
        unique (source_key)
);

create index if not exists idx_external_shift_deletion_requests_work_date
    on public.external_shift_deletion_requests (work_date);

create index if not exists idx_external_shift_deletion_requests_status
    on public.external_shift_deletion_requests (deletion_status);

create index if not exists idx_external_shift_deletion_requests_email
    on public.external_shift_deletion_requests (email);
