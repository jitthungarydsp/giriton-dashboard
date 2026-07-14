-- PeopleForce monthly documents and complaints.
-- Run this in Supabase SQL Editor before using the monthly TIG / settlement / invoice uploads.

create table if not exists public.peopleforce_documents (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text,
    document_type text not null,
    document_month date not null,
    title text,
    file_name text not null,
    mime_type text,
    file_size integer,
    file_content_base64 text not null,
    note text,
    uploaded_by text,
    uploaded_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create index if not exists idx_peopleforce_documents_courier_month
    on public.peopleforce_documents (courier_id, document_month, document_type);

create index if not exists idx_peopleforce_documents_uploaded_at
    on public.peopleforce_documents (uploaded_at desc);

create table if not exists public.peopleforce_complaints (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text,
    document_type text not null,
    document_month date not null,
    message text not null,
    status text not null default 'new',
    created_by text,
    created_at timestamptz not null default now()
);

alter table public.peopleforce_complaints
    add column if not exists admin_response text,
    add column if not exists responded_by text,
    add column if not exists responded_at timestamptz;

create index if not exists idx_peopleforce_complaints_courier_month
    on public.peopleforce_complaints (courier_id, document_month, document_type);

create index if not exists idx_peopleforce_complaints_created_at
    on public.peopleforce_complaints (created_at desc);

create table if not exists public.peopleforce_card_statuses (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    courier_name text,
    action_key text not null,
    document_month date not null,
    status text not null default 'open',
    status_note text,
    updated_by text,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    constraint peopleforce_card_statuses_status_check
        check (status in ('open', 'done')),
    constraint peopleforce_card_statuses_unique_key
        unique (courier_id, document_month, action_key)
);

create index if not exists idx_peopleforce_card_statuses_courier_month
    on public.peopleforce_card_statuses (courier_id, document_month, action_key);

create index if not exists idx_peopleforce_card_statuses_status
    on public.peopleforce_card_statuses (status);
