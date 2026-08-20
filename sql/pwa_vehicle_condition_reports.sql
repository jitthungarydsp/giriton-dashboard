begin;

alter table if exists public.pwa_devices
  drop constraint if exists pwa_devices_device_type_check;

alter table if exists public.pwa_devices
  add constraint pwa_devices_device_type_check
  check (device_type in ('phone', 'vehicle')) not valid;

alter table if exists public.pwa_device_condition_reports
  drop constraint if exists pwa_device_condition_reports_device_type_check;

alter table if exists public.pwa_device_condition_reports
  add constraint pwa_device_condition_reports_device_type_check
  check (device_type in ('phone', 'vehicle')) not valid;

alter table if exists public.pwa_device_condition_reports
  drop constraint if exists pwa_device_condition_reports_condition_status_check;

alter table if exists public.pwa_device_condition_reports
  add constraint pwa_device_condition_reports_condition_status_check
  check (condition_status in ('ok', 'scratched', 'dented', 'cracked', 'broken', 'missing_accessory', 'other')) not valid;

create index if not exists pwa_device_condition_reports_vehicle_lookup_idx
  on public.pwa_device_condition_reports (device_type, serial_number, reported_at desc);

alter table if exists public.pwa_device_condition_reports
  add column if not exists comparison_status text not null default 'not_run',
  add column if not exists comparison_note text not null default '',
  add column if not exists comparison_model text not null default '',
  add column if not exists compared_report_id uuid,
  add column if not exists comparison_checked_at timestamptz;

commit;
