begin;

-- Private bucket: the API serves files only after checking the PWA session.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'pwa-attachments',
  'pwa-attachments',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'application/octet-stream']::text[]
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

alter table public.pwa_device_condition_photos
  add column if not exists storage_bucket text,
  add column if not exists storage_path text,
  add column if not exists content_sha256 text;

alter table public.pwa_atm_payment
  add column if not exists storage_bucket text,
  add column if not exists storage_path text,
  add column if not exists content_sha256 text;

alter table public.courier_route_alert_photos
  add column if not exists storage_bucket text,
  add column if not exists storage_path text,
  add column if not exists content_sha256 text;

create index if not exists idx_pwa_device_condition_photos_storage_path
  on public.pwa_device_condition_photos (storage_bucket, storage_path)
  where storage_path is not null;

create index if not exists idx_pwa_atm_payment_storage_path
  on public.pwa_atm_payment (storage_bucket, storage_path)
  where storage_path is not null;

create index if not exists idx_courier_route_alert_photos_storage_path
  on public.courier_route_alert_photos (storage_bucket, storage_path)
  where storage_path is not null;

commit;

notify pgrst, 'reload schema';
