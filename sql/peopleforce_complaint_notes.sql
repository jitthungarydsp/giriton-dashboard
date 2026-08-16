create table if not exists public.peopleforce_complaint_notes (
    period_start date not null,
    courier_id text not null,
    note text not null default '',
    updated_by text,
    updated_at timestamptz not null default now(),
    primary key (period_start, courier_id)
);

comment on table public.peopleforce_complaint_notes is
    'Internal complaint note by courier and settlement month.';
comment on column public.peopleforce_complaint_notes.period_start is
    'First day of settlement month.';
comment on column public.peopleforce_complaint_notes.courier_id is
    'Courier identifier.';
comment on column public.peopleforce_complaint_notes.note is
    'Internal complaint note.';
