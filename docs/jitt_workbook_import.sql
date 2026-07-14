create table if not exists public.jitt_workbook_imports (
    source_name text not null default 'jitt-workbook',
    source_spreadsheet_id text not null,
    source_url text,
    workbook_title text,
    worksheet_name text not null,
    worksheet_gid text,
    detail_header_row integer not null default 23,
    detail_headers jsonb not null default '[]'::jsonb,
    top_rows_count integer not null default 0,
    detail_rows_count integer not null default 0,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id, worksheet_name)
);

create table if not exists public.jitt_workbook_main_raw (
    source_name text not null default 'jitt-workbook',
    source_spreadsheet_id text not null,
    source_url text,
    workbook_title text,
    worksheet_name text not null,
    worksheet_gid text,
    row_number integer not null,
    first_cell text,
    row_values jsonb not null default '[]'::jsonb,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id, worksheet_name, row_number)
);

create table if not exists public.jitt_workbook_detail_raw (
    source_name text not null default 'jitt-workbook',
    source_spreadsheet_id text not null,
    source_url text,
    workbook_title text,
    worksheet_name text not null,
    worksheet_gid text,
    row_number integer not null,
    row_data jsonb not null default '{}'::jsonb,
    row_values jsonb not null default '[]'::jsonb,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id, worksheet_name, row_number)
);

create index if not exists idx_jitt_workbook_main_sheet
    on public.jitt_workbook_main_raw (source_spreadsheet_id, worksheet_name);

create index if not exists idx_jitt_workbook_detail_sheet
    on public.jitt_workbook_detail_raw (source_spreadsheet_id, worksheet_name);

create index if not exists idx_jitt_workbook_detail_data
    on public.jitt_workbook_detail_raw using gin (row_data);
