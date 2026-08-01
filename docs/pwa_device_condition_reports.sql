create table if not exists public.pwa_devices (
    id bigserial primary key,
    device_type text not null default 'phone',
    serial_number text not null,
    imei text,
    status text not null default 'active',
    current_courier_id integer,
    current_courier_name text,
    note text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (device_type, serial_number)
);

create index if not exists idx_pwa_devices_current_courier
    on public.pwa_devices (current_courier_id, updated_at desc);

create table if not exists public.pwa_device_condition_reports (
    id bigserial primary key,
    device_id bigint references public.pwa_devices(id),
    device_type text not null default 'phone',
    serial_number text not null,
    imei text,
    courier_id integer not null,
    courier_name text,
    event_type text not null default 'inspection',
    condition_status text not null default 'ok',
    note text,
    photo_count integer not null default 0,
    reported_by text,
    reported_at timestamptz not null default now()
);

create index if not exists idx_pwa_device_condition_reports_device
    on public.pwa_device_condition_reports (device_type, serial_number, reported_at desc);

create index if not exists idx_pwa_device_condition_reports_courier
    on public.pwa_device_condition_reports (courier_id, reported_at desc);

create table if not exists public.pwa_device_condition_photos (
    id bigserial primary key,
    report_id bigint not null references public.pwa_device_condition_reports(id) on delete cascade,
    file_name text not null,
    mime_type text not null,
    file_size integer not null,
    file_content_base64 text not null,
    photo_label text,
    uploaded_at timestamptz not null default now()
);

create index if not exists idx_pwa_device_condition_photos_report
    on public.pwa_device_condition_photos (report_id, uploaded_at);

grant select, insert, update on public.pwa_devices to service_role;
grant usage, select on sequence public.pwa_devices_id_seq to service_role;

grant select, insert, update on public.pwa_device_condition_reports to service_role;
grant usage, select on sequence public.pwa_device_condition_reports_id_seq to service_role;

grant select, insert, update on public.pwa_device_condition_photos to service_role;
grant usage, select on sequence public.pwa_device_condition_photos_id_seq to service_role;
