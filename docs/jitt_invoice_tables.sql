create table if not exists public.jitt_invoice_imports (
    source_name text not null default 'jitt_invoice',
    source_spreadsheet_id text not null,
    source_url text,
    workbook_title text,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id)
);

create table if not exists public.jitt_invoice_summary_rows (
    source_name text not null default 'jitt_invoice',
    source_spreadsheet_id text not null,
    workbook_title text,
    worksheet_name text not null,
    row_number integer not null,
    metric_name text not null,
    total_value numeric,
    normal_value numeric,
    region_value numeric,
    express_value numeric,
    total_raw text,
    normal_raw text,
    region_raw text,
    express_raw text,
    row_values jsonb not null default '[]'::jsonb,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id, worksheet_name, row_number)
);

create table if not exists public.jitt_invoice_route_rows (
    source_name text not null default 'jitt_invoice',
    source_spreadsheet_id text not null,
    workbook_title text,
    worksheet_name text not null,
    row_number integer not null,
    location text,
    driver_name text,
    route_unique_id text,
    route_type text,
    dsp text,
    work_date date,
    orders numeric,
    routes numeric,
    tip_huf numeric,
    license_plate text,
    intern_extern_car text,
    fixed_rate_huf numeric,
    fuel_bonus_huf numeric,
    car_fridge_bonus_huf numeric,
    branding_huf numeric,
    delay_bonus_huf numeric,
    compliance_bonus_huf numeric,
    fill_rate_bonus_huf numeric,
    comment text,
    row_data jsonb not null default '{}'::jsonb,
    row_values jsonb not null default '[]'::jsonb,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id, worksheet_name, row_number)
);

create table if not exists public.jitt_invoice_final_routes (
    source_name text not null default 'jitt_invoice',
    source_spreadsheet_id text not null,
    workbook_title text,
    worksheet_name text not null,
    row_number integer not null,
    location text,
    driver_name text,
    route_unique_id text,
    route_type text,
    dsp text,
    work_date date,
    orders numeric,
    routes numeric,
    license_plate text,
    intern_extern_car text,
    fixed_rate_huf numeric,
    fuel_bonus_huf numeric,
    car_fridge_bonus_huf numeric,
    branding_huf numeric,
    delay_bonus_huf numeric,
    compliance_bonus_huf numeric,
    fill_rate_bonus_huf numeric,
    bonus_total_huf numeric,
    tip_huf numeric,
    route_total_without_tip_huf numeric,
    route_total_huf numeric,
    comment text,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id, worksheet_name, row_number)
);

create table if not exists public.jitt_invoice_bonus_routes (
    source_name text not null default 'jitt_invoice',
    source_spreadsheet_id text not null,
    workbook_title text,
    worksheet_name text not null,
    row_number integer not null,
    dsp text,
    site text,
    courier_id text,
    driver_name text,
    routes numeric,
    bonus_huf numeric,
    row_values jsonb not null default '[]'::jsonb,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id, worksheet_name, row_number)
);

create table if not exists public.jitt_invoice_penalties (
    source_name text not null default 'jitt_invoice',
    source_spreadsheet_id text not null,
    workbook_title text,
    worksheet_name text not null,
    row_number integer not null,
    penalty_type text,
    penalty_date date,
    courier_id text,
    driver_name text,
    dsp text,
    site text,
    note text,
    amount_huf numeric,
    extra_note text,
    row_values jsonb not null default '[]'::jsonb,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (source_name, source_spreadsheet_id, worksheet_name, row_number)
);

create table if not exists public.jitt_invoice_contract_bonus_rules (
    rule_id text primary key,
    metric_type text not null,
    metric_name text not null,
    level_number integer not null,
    level_name text not null,
    threshold_label text not null,
    threshold_min_pct numeric,
    threshold_max_pct numeric,
    duration_hours numeric not null,
    duration_label text not null,
    amount_huf numeric not null,
    source_note text,
    imported_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.bill_jitt_invoice_manual_items (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'manual_invoice',
    item_date date not null,
    worksheet_name text,
    driver_name text not null,
    item_type text not null,
    item_label text not null,
    amount_huf numeric not null default 0,
    note text,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.jitt_invoice_manual_items (
    id uuid primary key default gen_random_uuid(),
    source_name text not null default 'manual_invoice',
    item_date date not null,
    worksheet_name text,
    driver_name text not null,
    item_type text not null,
    item_label text not null,
    amount_huf numeric not null default 0,
    note text,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_jitt_invoice_summary_sheet
    on public.jitt_invoice_summary_rows (source_spreadsheet_id, worksheet_name);

create index if not exists idx_jitt_invoice_route_driver_date
    on public.jitt_invoice_route_rows (driver_name, work_date);

create index if not exists idx_jitt_invoice_route_unique
    on public.jitt_invoice_route_rows (route_unique_id);

create index if not exists idx_jitt_invoice_final_driver_date
    on public.jitt_invoice_final_routes (driver_name, work_date);

create index if not exists idx_jitt_invoice_bonus_driver
    on public.jitt_invoice_bonus_routes (driver_name);

create index if not exists idx_jitt_invoice_penalties_driver
    on public.jitt_invoice_penalties (driver_name, penalty_date);

create index if not exists idx_bill_jitt_invoice_manual_driver_date
    on public.bill_jitt_invoice_manual_items (driver_name, item_date);

create index if not exists idx_jitt_invoice_manual_driver_date
    on public.jitt_invoice_manual_items (driver_name, item_date);
