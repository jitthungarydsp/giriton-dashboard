begin;

create table if not exists settlement.courier_expense_request (
  id uuid primary key default gen_random_uuid(),
  courier_id text not null,
  courier_name text not null default '',
  request_type text not null default 'fuel',
  document_month date not null,
  process_id text not null,
  license_plate text not null default '',
  odometer_km integer,
  amount_huf integer not null default 0,
  invoice_number text not null default '',
  note text not null default '',
  document_id text,
  status text not null default 'approved',
  requested_by text not null default '',
  requested_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  paid_at timestamptz,
  paid_by text,
  rejected_at timestamptz,
  rejected_by text,
  rejection_note text not null default '',
  constraint courier_expense_request_process_unique unique (process_id),
  constraint courier_expense_request_type_check check (request_type in ('fuel', 'other')),
  constraint courier_expense_request_amount_positive check (amount_huf > 0)
);

create index if not exists courier_expense_request_courier_month_idx
  on settlement.courier_expense_request (courier_id, document_month);

create index if not exists courier_expense_request_status_idx
  on settlement.courier_expense_request (status);

commit;
