begin;

create table if not exists public.coordinator_shift_email_notices (
    mailbox text not null,
    gmail_id text not null,
    gmail_thread_id text not null,
    subject text not null,
    sender text not null,
    received_at timestamptz not null,
    event_type text not null check (event_type in ('late', 'absence')),
    courier_label text not null,
    courier_id text,
    late_occurrence integer check (late_occurrence is null or (late_occurrence > 0 and event_type = 'late')),
    shift_label text not null,
    body_text text not null,
    body_html text not null,
    imported_at timestamptz not null default now(),
    primary key (mailbox, gmail_id)
);

create index if not exists coordinator_shift_email_notices_received_idx
    on public.coordinator_shift_email_notices (received_at desc);

alter table public.coordinator_shift_email_notices enable row level security;
revoke all on public.coordinator_shift_email_notices from public, anon, authenticated;
grant select, insert on public.coordinator_shift_email_notices to service_role;

commit;
