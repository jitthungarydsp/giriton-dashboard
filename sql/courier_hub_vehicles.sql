-- Courier Hub vehicles endpoint raw storage.
-- The response_json columns intentionally preserve the complete upstream payload
-- so new fields can be used later without another historical import.

create table if not exists public.courier_hub_vehicle_raw (
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null,
    vehicle_id bigint not null,
    registration_number text,
    vehicle_type text,
    status text,
    removed boolean,
    list_request_url text not null,
    detail_request_url text,
    list_status_code integer not null,
    detail_status_code integer,
    list_response_json jsonb not null,
    detail_response_json jsonb,
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (warehouse_id, dsp_id, vehicle_id)
);

create table if not exists public.courier_hub_vehicle_history_raw (
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null,
    vehicle_id bigint not null,
    history_key text not null,
    history_record_id text,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (warehouse_id, dsp_id, vehicle_id, history_key)
);

create table if not exists public.courier_hub_vehicle_documents_raw (
    warehouse_id integer not null,
    warehouse_code text not null,
    dsp_id integer not null,
    vehicle_id bigint not null,
    document_key text not null,
    document_id text,
    document_type text,
    request_url text not null,
    status_code integer not null,
    response_json jsonb not null,
    fetched_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (warehouse_id, dsp_id, vehicle_id, document_key)
);

create index if not exists courier_hub_vehicle_raw_registration_idx
    on public.courier_hub_vehicle_raw (registration_number);
create index if not exists courier_hub_vehicle_raw_list_idx
    on public.courier_hub_vehicle_raw (warehouse_code, registration_number, vehicle_id);
create index if not exists courier_hub_vehicle_raw_updated_idx
    on public.courier_hub_vehicle_raw (updated_at desc);
create index if not exists courier_hub_vehicle_history_vehicle_idx
    on public.courier_hub_vehicle_history_raw (vehicle_id, fetched_at desc);
create index if not exists courier_hub_vehicle_documents_vehicle_idx
    on public.courier_hub_vehicle_documents_raw (vehicle_id, fetched_at desc);

grant select, insert, update, delete on public.courier_hub_vehicle_raw to service_role;
grant select, insert, update, delete on public.courier_hub_vehicle_history_raw to service_role;
grant select, insert, update, delete on public.courier_hub_vehicle_documents_raw to service_role;
