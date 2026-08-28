begin;

create table if not exists public.pwa_atm_payment (
  id uuid primary key default gen_random_uuid(),
  courier_id text not null,
  courier_name text not null default '',
  amount_huf integer not null,
  invoice_number text not null default '',
  note text not null default '',
  file_name text not null default '',
  mime_type text not null default '',
  file_size integer not null default 0,
  file_content_base64 text not null default '',
  status text not null default 'submitted',
  paid_at timestamptz not null default now(),
  created_by text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint pwa_atm_payment_amount_positive check (amount_huf > 0),
  constraint pwa_atm_payment_status_check check (status in ('submitted', 'reviewed', 'rejected'))
);

create index if not exists pwa_atm_payment_courier_paid_at_idx
  on public.pwa_atm_payment (courier_id, paid_at desc);

commit;
