create extension if not exists pgcrypto;

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

create index if not exists idx_bill_jitt_invoice_manual_driver_date
    on public.bill_jitt_invoice_manual_items (driver_name, item_date);

create index if not exists idx_jitt_invoice_manual_driver_date
    on public.jitt_invoice_manual_items (driver_name, item_date);

notify pgrst, 'reload schema';
