begin;

create extension if not exists pgcrypto;
create schema if not exists settlement;

create table if not exists settlement.processing_run (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null,
    status text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    total_sheets integer not null default 0,
    recognized_sheets integer not null default 0,
    unknown_sheets integer not null default 0,
    total_rows integer not null default 0,
    accepted_rows integer not null default 0,
    rejected_rows integer not null default 0,
    critical_errors integer not null default 0,
    summary jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint processing_run_status_check check (
        status in (
            'running',
            'completed',
            'completed_with_warnings',
            'failed'
        )
    )
);

create table if not exists settlement.sheet_processing_result (
    id uuid primary key default gen_random_uuid(),
    processing_run_id uuid not null,
    session_id uuid not null,
    sheet_name text not null,
    detected_type text,
    header_row integer,
    confidence numeric,
    total_rows integer not null default 0,
    accepted_rows integer not null default 0,
    rejected_rows integer not null default 0,
    status text not null,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint sheet_processing_result_run_fk
        foreign key (processing_run_id)
        references settlement.processing_run (id)
        on delete cascade,
    constraint sheet_processing_result_run_sheet_unique unique (
        processing_run_id,
        sheet_name
    )
);

create table if not exists settlement.validation_error (
    id uuid primary key default gen_random_uuid(),
    processing_run_id uuid not null,
    session_id uuid not null,
    sheet_name text,
    source_row_no integer,
    error_code text not null,
    severity text not null,
    message text not null,
    raw_data jsonb,
    created_at timestamptz not null default now(),
    constraint validation_error_severity_check check (
        severity in ('info', 'warning', 'error', 'critical')
    ),
    constraint validation_error_run_fk
        foreign key (processing_run_id)
        references settlement.processing_run (id)
        on delete cascade
);

create table if not exists settlement.jit_row (
    id uuid primary key default gen_random_uuid(),
    processing_run_id uuid not null,
    session_id uuid not null,
    source_sheet text not null,
    source_row_no integer not null,
    normalized_data jsonb not null,
    created_at timestamptz not null default now(),
    constraint jit_row_run_fk
        foreign key (processing_run_id)
        references settlement.processing_run (id)
        on delete cascade,
    constraint jit_row_source_unique unique (
        session_id,
        source_sheet,
        source_row_no
    )
);

create table if not exists settlement.penalty_row (
    id uuid primary key default gen_random_uuid(),
    processing_run_id uuid not null,
    session_id uuid not null,
    source_sheet text not null,
    source_row_no integer not null,
    normalized_data jsonb not null,
    created_at timestamptz not null default now(),
    constraint penalty_row_run_fk
        foreign key (processing_run_id)
        references settlement.processing_run (id)
        on delete cascade,
    constraint penalty_row_source_unique unique (
        session_id,
        source_sheet,
        source_row_no
    )
);

create table if not exists settlement.atm_balance_row (
    id uuid primary key default gen_random_uuid(),
    processing_run_id uuid not null,
    session_id uuid not null,
    source_sheet text not null,
    source_row_no integer not null,
    normalized_data jsonb not null,
    created_at timestamptz not null default now(),
    constraint atm_balance_row_run_fk
        foreign key (processing_run_id)
        references settlement.processing_run (id)
        on delete cascade,
    constraint atm_balance_row_source_unique unique (
        session_id,
        source_sheet,
        source_row_no
    )
);

create table if not exists settlement.bonus_route_row (
    id uuid primary key default gen_random_uuid(),
    processing_run_id uuid not null,
    session_id uuid not null,
    source_sheet text not null,
    source_row_no integer not null,
    normalized_data jsonb not null,
    created_at timestamptz not null default now(),
    constraint bonus_route_row_run_fk
        foreign key (processing_run_id)
        references settlement.processing_run (id)
        on delete cascade,
    constraint bonus_route_row_source_unique unique (
        session_id,
        source_sheet,
        source_row_no
    )
);

create table if not exists settlement.performance_indicator_row (
    id uuid primary key default gen_random_uuid(),
    processing_run_id uuid not null,
    session_id uuid not null,
    source_sheet text not null,
    source_row_no integer not null,
    normalized_data jsonb not null,
    created_at timestamptz not null default now(),
    constraint performance_indicator_row_run_fk
        foreign key (processing_run_id)
        references settlement.processing_run (id)
        on delete cascade,
    constraint performance_indicator_row_source_unique unique (
        session_id,
        source_sheet,
        source_row_no
    )
);

create index if not exists processing_run_session_id_idx
    on settlement.processing_run (session_id);

create index if not exists sheet_processing_result_session_id_idx
    on settlement.sheet_processing_result (session_id);
create index if not exists sheet_processing_result_run_id_idx
    on settlement.sheet_processing_result (processing_run_id);
create index if not exists sheet_processing_result_detected_type_idx
    on settlement.sheet_processing_result (detected_type);

create index if not exists validation_error_session_id_idx
    on settlement.validation_error (session_id);
create index if not exists validation_error_run_id_idx
    on settlement.validation_error (processing_run_id);
create index if not exists validation_error_severity_idx
    on settlement.validation_error (severity);

create index if not exists jit_row_session_id_idx
    on settlement.jit_row (session_id);
create index if not exists jit_row_run_id_idx
    on settlement.jit_row (processing_run_id);
create index if not exists jit_row_source_idx
    on settlement.jit_row (source_sheet, source_row_no);

create index if not exists penalty_row_session_id_idx
    on settlement.penalty_row (session_id);
create index if not exists penalty_row_run_id_idx
    on settlement.penalty_row (processing_run_id);
create index if not exists penalty_row_source_idx
    on settlement.penalty_row (source_sheet, source_row_no);

create index if not exists atm_balance_row_session_id_idx
    on settlement.atm_balance_row (session_id);
create index if not exists atm_balance_row_run_id_idx
    on settlement.atm_balance_row (processing_run_id);
create index if not exists atm_balance_row_source_idx
    on settlement.atm_balance_row (source_sheet, source_row_no);

create index if not exists bonus_route_row_session_id_idx
    on settlement.bonus_route_row (session_id);
create index if not exists bonus_route_row_run_id_idx
    on settlement.bonus_route_row (processing_run_id);
create index if not exists bonus_route_row_source_idx
    on settlement.bonus_route_row (source_sheet, source_row_no);

create index if not exists performance_indicator_row_session_id_idx
    on settlement.performance_indicator_row (session_id);
create index if not exists performance_indicator_row_run_id_idx
    on settlement.performance_indicator_row (processing_run_id);
create index if not exists performance_indicator_row_source_idx
    on settlement.performance_indicator_row (
        source_sheet,
        source_row_no
    );

grant usage on schema settlement to service_role;
grant select, insert, update, delete
    on table
        settlement.processing_run,
        settlement.sheet_processing_result,
        settlement.validation_error,
        settlement.jit_row,
        settlement.penalty_row,
        settlement.atm_balance_row,
        settlement.bonus_route_row,
        settlement.performance_indicator_row
    to service_role;
grant usage, select
    on all sequences in schema settlement
    to service_role;

alter default privileges in schema settlement
    grant select, insert, update, delete on tables to service_role;
alter default privileges in schema settlement
    grant usage, select on sequences to service_role;

notify pgrst, 'reload schema';

commit;
