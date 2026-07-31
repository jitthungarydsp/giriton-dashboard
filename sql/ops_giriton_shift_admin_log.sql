create table if not exists public.ops_giriton_shift_admin_log (
  id uuid primary key,
  source_name text not null default 'giriton-admin-page',
  action text not null,
  status text not null,
  actor text,
  message text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_ops_giriton_shift_admin_log_created_at
  on public.ops_giriton_shift_admin_log (created_at desc);

create index if not exists idx_ops_giriton_shift_admin_log_action
  on public.ops_giriton_shift_admin_log (action);

create index if not exists idx_ops_giriton_shift_admin_log_status
  on public.ops_giriton_shift_admin_log (status);
