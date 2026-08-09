create schema if not exists settlement;

create table if not exists settlement.mobile_settlement_breakdown_overrides (
    period_start date not null,
    courier_id text not null,
    item_key text not null,
    item_label text not null,
    amount_value numeric not null default 0,
    amount_kind text not null default 'huf',
    note text,
    updated_by text,
    updated_at timestamptz not null default now(),
    primary key (period_start, courier_id, item_key)
);

drop view if exists settlement.vw_legacy_tig_invoice_audit;

create or replace view settlement.vw_legacy_tig_invoice_audit as
with settlement_months as (
    select distinct
        coalesce(nullif(s.courier_id, ''), 'name:' || lower(trim(s.driver_name))) as courier_id,
        s.driver_name as courier_name,
        s.period_start::date as period_start,
        s.period_end::date as period_end
    from settlement.courier_settlement_summary s
),
tig as (
    select
        o.courier_id,
        o.period_start::date as period_start,
        max(o.amount_value) filter (where o.item_key = 'tig_final_total') as regi_rendszer_tig_osszeg,
        max(o.updated_at) as tig_updated_at,
        jsonb_agg(
            jsonb_build_object(
                'item_key', o.item_key,
                'item_label', o.item_label,
                'amount_value', o.amount_value,
                'note', o.note,
                'updated_at', o.updated_at
            )
            order by case when o.item_key = 'tig_final_total' then 1 else 0 end, o.item_key
        ) filter (where o.item_key like 'tig_%') as tig_rows
    from settlement.mobile_settlement_breakdown_overrides o
    where o.item_key like 'tig_%'
    group by o.courier_id, o.period_start
),
invoice_documents as (
    select distinct on (d.courier_id, date_trunc('month', d.document_month::date)::date)
        d.courier_id,
        date_trunc('month', d.document_month::date)::date as period_start,
        d.id::text as uploaded_invoice_document_id,
        coalesce(
            (regexp_match(
                concat_ws(' ', d.note, d.title, d.file_name),
                '(?:számlaszám|szamlaszam|sorszám|sorszam)\s*:?\s*([A-Za-z0-9/_-]{3,})',
                'i'
            ))[1],
            (regexp_match(
                concat_ws(' ', d.note, d.title, d.file_name),
                '\m([A-Z]{1,5}[-_/]?\d{3,})\M',
                'i'
            ))[1],
            ''
        ) as feltoltott_szamla_szam,
        coalesce(
            nullif(regexp_replace(
                replace(replace(coalesce((regexp_match(
                    d.note,
                    'brutt[óo]\s+[öo]sszesen\s*:?\s*([0-9\s.,]+)\s*Ft',
                    'i'
                ))[1], ''), ' ', ''), ',', '.'),
                '[^0-9.]',
                '',
                'g'
            ), '')::numeric,
            nullif(regexp_replace(
                replace(replace(coalesce((regexp_match(
                    d.note,
                    '[öo]sszeg\s*:?\s*([0-9\s.,]+)\s*Ft',
                    'i'
                ))[1], ''), ' ', ''), ',', '.'),
                '[^0-9.]',
                '',
                'g'
            ), '')::numeric,
            0
        ) as feltoltott_szamla_osszeg,
        d.title as feltoltott_szamla_cim,
        d.file_name as feltoltott_szamla_fajl,
        d.note as feltoltott_szamla_megjegyzes,
        d.uploaded_at as feltoltott_szamla_feltoltve
    from public.peopleforce_documents d
    where lower(coalesce(d.document_type, '')) = 'invoice'
       or lower(concat_ws(' ', d.document_type, d.title, d.file_name)) like '%számla%'
       or lower(concat_ws(' ', d.document_type, d.title, d.file_name)) like '%szamla%'
    order by
        d.courier_id,
        date_trunc('month', d.document_month::date)::date,
        d.uploaded_at desc,
        d.id desc
)
select
    m.courier_id,
    m.courier_name,
    m.period_start,
    m.period_end,
    coalesce(t.regi_rendszer_tig_osszeg, 0) as regi_rendszer_tig_osszeg,
    coalesce(i.feltoltott_szamla_szam, '') as feltoltott_szamla_szam,
    coalesce(i.feltoltott_szamla_osszeg, 0) as feltoltott_szamla_osszeg,
    i.uploaded_invoice_document_id,
    i.feltoltott_szamla_cim,
    i.feltoltott_szamla_fajl,
    i.feltoltott_szamla_megjegyzes,
    i.feltoltott_szamla_feltoltve,
    t.tig_updated_at,
    coalesce(t.tig_rows, '[]'::jsonb) as tig_rows
from settlement_months m
left join tig t
  on t.courier_id = m.courier_id
 and t.period_start = m.period_start
left join invoice_documents i
  on i.courier_id = m.courier_id
 and i.period_start = m.period_start;

grant select on settlement.vw_legacy_tig_invoice_audit to service_role;
grant select on settlement.vw_legacy_tig_invoice_audit to authenticated;

notify pgrst, 'reload schema';
