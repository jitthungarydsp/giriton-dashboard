begin;

create table if not exists public.complaint_email_responses (
    mailbox text not null,
    gmail_id text not null,
    gmail_thread_id text not null,
    subject text not null,
    sender text not null,
    received_at timestamptz not null,
    body_text text not null,
    body_html text not null,
    imported_at timestamptz not null default now(),
    primary key (mailbox, gmail_id)
);

create index if not exists complaint_email_responses_received_idx
    on public.complaint_email_responses (received_at desc);

alter table public.complaint_email_responses enable row level security;
revoke all on public.complaint_email_responses from public, anon, authenticated;
grant select, insert on public.complaint_email_responses to service_role;

commit;
