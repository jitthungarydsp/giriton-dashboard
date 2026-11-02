-- Run after pwa_invoice_raw_phase1.sql. No legacy settlement tables are used.
begin;
alter table public."PWA_INVOICE_RAW" add column if not exists deleted_at timestamptz;

create table if not exists public."PWA_INVOICE_WORK" (
    settlement_month date primary key check (extract(day from settlement_month) = 1),
    id uuid not null unique,
    session_id text not null unique,
    source_upload_id uuid not null references public."PWA_INVOICE_RAW"(id),
    source_session_id text not null,
    source_file_name text not null,
    file_sha256 text not null,
    raw_data jsonb not null check (jsonb_typeof(raw_data->'sheets') = 'array'),
    sheet_count integer not null,
    raw_row_count integer not null,
    created_by text not null,
    created_at timestamptz not null default now()
);
alter table public."PWA_INVOICE_WORK" enable row level security;
revoke all on public."PWA_INVOICE_WORK" from public, anon, authenticated;
grant select on public."PWA_INVOICE_WORK" to service_role;

create or replace function public.pwa_invoice_work_select(
    p_month date, p_source_id uuid, p_request_id uuid, p_expected_id uuid, p_actor text
) returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare
    source public."PWA_INVOICE_RAW"%rowtype;
    current_work public."PWA_INVOICE_WORK"%rowtype;
begin
    if p_month is null or extract(day from p_month) <> 1 or p_request_id is null then
        raise exception 'Érvénytelen munkamenet.';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('pwa-invoice-month:' || p_month::text, 0));
    select * into current_work from public."PWA_INVOICE_WORK" where settlement_month = p_month;
    if current_work.id = p_request_id then
        if current_work.source_upload_id <> p_source_id then
            return jsonb_build_object('conflict', true);
        end if;
        return to_jsonb(current_work) - 'raw_data';
    end if;
    -- Compare-and-swap: another admin or browser tab cannot replace a newer selection.
    if current_work.id is distinct from p_expected_id then
        return jsonb_build_object('conflict', true);
    end if;
    select * into source from public."PWA_INVOICE_RAW"
        where id = p_source_id and settlement_month = p_month and deleted_at is null;
    if not found then
        return jsonb_build_object('missing', true);
    end if;
    if current_work.source_upload_id = p_source_id then
        return to_jsonb(current_work) - 'raw_data';
    end if;
    insert into public."PWA_INVOICE_WORK" (
        settlement_month,id,session_id,source_upload_id,source_session_id,source_file_name,
        file_sha256,raw_data,sheet_count,raw_row_count,created_by
    ) values (
        p_month,p_request_id,'JITT_WORK_' || to_char(p_month,'YYYY_MM') || '_' || replace(p_request_id::text,'-',''),
        source.id,source.session_id,source.source_file_name,source.file_sha256,
        source.raw_data,source.sheet_count,source.raw_row_count,p_actor
    ) on conflict (settlement_month) do update set
        id=excluded.id,session_id=excluded.session_id,source_upload_id=excluded.source_upload_id,
        source_session_id=excluded.source_session_id,source_file_name=excluded.source_file_name,
        file_sha256=excluded.file_sha256,raw_data=excluded.raw_data,sheet_count=excluded.sheet_count,
        raw_row_count=excluded.raw_row_count,created_by=excluded.created_by,created_at=now()
    returning * into current_work;
    return to_jsonb(current_work) - 'raw_data';
end;
$$;

create or replace function public.pwa_invoice_raw_delete(p_month date, p_ids uuid[])
returns jsonb language plpgsql security definer set search_path = public, pg_temp as $$
declare n integer;
begin
    if p_month is null or extract(day from p_month) <> 1 or coalesce(cardinality(p_ids),0) < 1
       or cardinality(p_ids) > 100 then raise exception 'Érvénytelen törlési lista.'; end if;
    perform pg_advisory_xact_lock(hashtextextended('pwa-invoice-month:' || p_month::text, 0));
    if exists (select 1 from unnest(p_ids) selected(id) where not exists (
        select 1 from public."PWA_INVOICE_RAW" r where r.id=selected.id and r.settlement_month=p_month
    )) then return jsonb_build_object('missing',true); end if;
    if exists (select 1 from public."PWA_INVOICE_WORK" where settlement_month=p_month and source_upload_id=any(p_ids)) then
        return jsonb_build_object('activeSource',true);
    end if;
    -- Recoverable list deletion. Preserve original files and RAW evidence.
    update public."PWA_INVOICE_RAW" set deleted_at=now()
        where settlement_month=p_month and id=any(p_ids) and deleted_at is null;
    get diagnostics n = row_count;
    return jsonb_build_object('ok',true,'deletedCount',n);
end;
$$;
revoke all on function public.pwa_invoice_work_select(date,uuid,uuid,uuid,text) from public,anon,authenticated;
revoke all on function public.pwa_invoice_raw_delete(date,uuid[]) from public,anon,authenticated;
grant execute on function public.pwa_invoice_work_select(date,uuid,uuid,uuid,text) to service_role;
grant execute on function public.pwa_invoice_raw_delete(date,uuid[]) to service_role;
notify pgrst,'reload schema';
commit;
