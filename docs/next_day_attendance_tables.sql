create table if not exists public.ops_dsp_next_day_shift_snapshots (
    snapshot_date date not null,
    work_date date not null,
    snapshot_fetched_at timestamptz not null,
    organization_id text not null,
    dsp_id text not null,
    dsp_name text,
    courier_id bigint not null,
    courier_name text,
    warehouse_name text,
    shift_id bigint not null,
    shift_name text,
    shift_start timestamptz not null,
    shift_end timestamptz,
    raw_shift jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (snapshot_date, work_date, courier_id, shift_id)
);

create index if not exists idx_ops_dsp_next_day_shift_work_date
    on public.ops_dsp_next_day_shift_snapshots (work_date, shift_start);

create table if not exists public.ops_dsp_shift_attendance_checks (
    work_date date not null,
    courier_id bigint not null,
    shift_id bigint not null,
    snapshot_date date not null,
    snapshot_fetched_at timestamptz not null,
    checked_at timestamptz not null,
    organization_id text not null,
    dsp_id text not null,
    courier_name text,
    warehouse_name text,
    shift_name text,
    shift_start timestamptz not null,
    shift_end timestamptz,
    current_shift_found boolean not null default false,
    available_for_shift_since timestamptz,
    evidence_route_ids jsonb not null default '[]'::jsonb,
    grace_minutes integer not null default 30,
    minutes_after_start integer,
    attendance_status text not null,
    status_reason text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (work_date, courier_id, shift_id)
);

create index if not exists idx_ops_dsp_shift_attendance_status
    on public.ops_dsp_shift_attendance_checks (
        work_date,
        attendance_status,
        shift_start
    );

comment on table public.ops_dsp_next_day_shift_snapshots is
'OPS: Elozo nap rogzitett kovetkezo napi DSP muszaklista.';

comment on table public.ops_dsp_shift_attendance_checks is
'OPS: A rogzitett muszaklista es a targynapi attendance API osszehasonlitasa.';
