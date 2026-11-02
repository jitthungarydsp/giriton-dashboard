-- Phase 1 only: isolated workbook archive. No legacy settlement table/RPC is changed.
begin;

create table if not exists public."PWA_INVOICE_RAW" (
    id uuid primary key,
    session_id text not null unique,
    settlement_month date not null check (extract(day from settlement_month) = 1),
    source_file_name text not null,
    original_storage_path text not null unique,
    file_sha256 text not null check (file_sha256 ~ '^[0-9a-f]{64}$'),
    file_size_bytes bigint not null check (file_size_bytes > 0),
    raw_data jsonb not null check (jsonb_typeof(raw_data) = 'object'),
    sheet_count integer not null check (sheet_count > 0),
    raw_row_count integer not null check (raw_row_count >= 0),
    status text not null default 'saved' check (status = 'saved'),
    created_by text not null,
    created_at timestamptz not null default now()
);
create index if not exists pwa_invoice_raw_month_idx
    on public."PWA_INVOICE_RAW" (settlement_month, created_at desc, id);
alter table public."PWA_INVOICE_RAW" enable row level security;
revoke all on public."PWA_INVOICE_RAW" from public, anon, authenticated;
grant select on public."PWA_INVOICE_RAW" to service_role;

create or replace function public.pwa_invoice_raw_save(
    p_id uuid, p_month date, p_file_name text, p_storage_path text,
    p_sha256 text, p_byte_size bigint, p_raw_data jsonb, p_created_by text
) returns jsonb
language plpgsql security definer set search_path = public, pg_temp as $$
declare
    saved public."PWA_INVOICE_RAW"%rowtype;
    session_name text;
    sheets integer;
    rows_total integer;
    attempt integer;
begin
    if p_id is null or p_month is null or extract(day from p_month) <> 1 then
        raise exception 'Érvénytelen feltöltési azonosító vagy hónap.';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(p_id::text, 0));
    select * into saved from public."PWA_INVOICE_RAW" where id = p_id;
    if found then
        if saved.file_sha256 <> p_sha256 or saved.settlement_month <> p_month
           or saved.source_file_name <> p_file_name or saved.file_size_bytes <> p_byte_size then
            raise exception 'A kérésazonosító másik feltöltéshez tartozik.' using errcode = '22023';
        end if;
        return to_jsonb(saved) - 'raw_data' - 'original_storage_path';
    end if;
    if jsonb_typeof(p_raw_data->'sheets') is distinct from 'array'
       or jsonb_array_length(p_raw_data->'sheets') = 0 then
        raise exception 'Hiányzik a RAW munkalaplista.';
    end if;
    if p_storage_path not like 'pwa-invoice-raw/' || p_id::text || '/original.%'
       or p_storage_path like '%..%' then
        raise exception 'Érvénytelen fájlelérési út.';
    end if;
    sheets := jsonb_array_length(p_raw_data->'sheets');
    select coalesce(sum(jsonb_array_length(sheet->'rows')), 0)::integer
        into rows_total from jsonb_array_elements(p_raw_data->'sheets') sheet;
    for attempt in 1..30 loop
        session_name := 'JITT_' || to_char(p_month, 'YYYY_MM') || '_' || (100000 + floor(random() * 900000))::integer;
        begin
            insert into public."PWA_INVOICE_RAW" (
                id, session_id, settlement_month, source_file_name, original_storage_path,
                file_sha256, file_size_bytes, raw_data, sheet_count, raw_row_count, created_by
            ) values (
                p_id, session_name, p_month, p_file_name, p_storage_path,
                p_sha256, p_byte_size, p_raw_data, sheets, rows_total, p_created_by
            ) returning * into saved;
            return to_jsonb(saved) - 'raw_data' - 'original_storage_path';
        exception when unique_violation then
            if exists (select 1 from public."PWA_INVOICE_RAW" where id = p_id or original_storage_path = p_storage_path) then
                raise;
            end if;
            -- Human-readable six-digit session collision: choose another number.
        end;
    end loop;
    raise exception 'Nem sikerült egyedi sessionazonosítót létrehozni.';
end;
$$;
revoke all on function public.pwa_invoice_raw_save(uuid,date,text,text,text,bigint,jsonb,text) from public, anon, authenticated;
grant execute on function public.pwa_invoice_raw_save(uuid,date,text,text,text,bigint,jsonb,text) to service_role;
notify pgrst, 'reload schema';
commit;
