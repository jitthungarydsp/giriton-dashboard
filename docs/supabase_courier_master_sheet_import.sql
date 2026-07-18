-- Courier master staging/import table.
-- One row = one source row from the legacy courier registration/billing sheet.
-- This table intentionally keeps the full raw row, so later enrichment/mapping can
-- happen without losing source columns.
--
-- Run this in Supabase SQL Editor before the first import.

create table if not exists public.courier_master_sheet_import (
    id bigserial primary key,
    import_batch_id text not null,
    source_name text not null default 'courier_master_sheet_import',
    source_file text not null,
    source_row_number integer not null,
    courier_id text,
    courier_name text,
    email text,
    phone_number text,
    company_name text,
    tax_number text,
    company_address text,
    bank_account_number text,
    billing_email text,
    source_timestamp text,
    raw_payload jsonb not null,
    imported_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint courier_master_sheet_import_source_row_uq
        unique (source_file, source_row_number)
);

create index if not exists idx_courier_master_sheet_import_batch
    on public.courier_master_sheet_import (import_batch_id);

create index if not exists idx_courier_master_sheet_import_courier_id
    on public.courier_master_sheet_import (courier_id);

create index if not exists idx_courier_master_sheet_import_email
    on public.courier_master_sheet_import (email);

create index if not exists idx_courier_master_sheet_import_name
    on public.courier_master_sheet_import (courier_name);

-- If the table already exists, run-safe schema extension.
alter table public.courier_master_sheet_import
    add column if not exists company_name text,
    add column if not exists tax_number text,
    add column if not exists company_address text,
    add column if not exists bank_account_number text,
    add column if not exists billing_email text;

create index if not exists idx_courier_master_sheet_import_tax_number
    on public.courier_master_sheet_import (tax_number);
