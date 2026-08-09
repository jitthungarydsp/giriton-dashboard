create schema if not exists settlement;

drop view if exists settlement.vw_legacy_paid_invoice_dedup;

create or replace view settlement.vw_legacy_paid_invoice_dedup as
with paid_statuses as (
    select
        s.*,
        row_number() over (
            partition by s.courier_id, s.document_month::date
            order by s.updated_at desc, s.id desc
        ) as rn
    from public.peopleforce_card_statuses s
    where s.action_key like 'invoice_payment%'
      and s.status = 'done'
),
latest_paid as (
    select
        p.id as payment_status_id,
        p.courier_id,
        p.courier_name,
        p.document_month::date as document_month,
        p.action_key,
        p.status,
        p.status_note,
        p.updated_at as payment_updated_at,
        p.updated_by as payment_updated_by,
        coalesce(
            nullif(regexp_replace(
                replace(replace(coalesce((regexp_match(
                    p.status_note,
                    'Kifizetve\s*:?\s*([0-9\s.,]+)\s*Ft',
                    'i'
                ))[1], ''), ' ', ''), ',', '.'),
                '[^0-9.]',
                '',
                'g'
            ), '')::numeric,
            nullif(regexp_replace(
                replace(replace(coalesce((regexp_match(
                    p.status_note,
                    '([0-9\s.,]+)\s*Ft',
                    'i'
                ))[1], ''), ' ', ''), ',', '.'),
                '[^0-9.]',
                '',
                'g'
            ), '')::numeric,
            0
        ) as paid_amount_huf
    from paid_statuses p
    where p.rn = 1
),
invoice_documents as (
    select
        d.*,
        row_number() over (
            partition by d.courier_id, d.document_month::date
            order by d.uploaded_at desc, d.id desc
        ) as rn
    from public.peopleforce_documents d
    where lower(coalesce(d.document_type, '')) = 'invoice'
       or lower(concat_ws(' ', d.document_type, d.title, d.file_name)) like '%számla%'
       or lower(concat_ws(' ', d.document_type, d.title, d.file_name)) like '%szamla%'
),
latest_invoice as (
    select
        i.id as invoice_document_id,
        i.courier_id,
        i.document_month::date as document_month,
        i.title as invoice_title,
        i.file_name as invoice_file_name,
        i.note as invoice_note,
        i.uploaded_at as invoice_uploaded_at,
        i.uploaded_by as invoice_uploaded_by,
        coalesce(
            (regexp_match(
                concat_ws(' ', i.note, i.title, i.file_name),
                '(?:számlaszám|szamlaszam|sorszám|sorszam)\s*:?\s*([A-Za-z0-9/_-]{3,})',
                'i'
            ))[1],
            (regexp_match(
                concat_ws(' ', i.note, i.title, i.file_name),
                '\m([A-Z]{1,5}[-_/]?\d{3,})\M',
                'i'
            ))[1],
            ''
        ) as invoice_number,
        coalesce(
            nullif(regexp_replace(
                replace(replace(coalesce((regexp_match(
                    i.note,
                    'brutt[óo]\s+[öo]sszesen\s*:?\s*([0-9\s.,]+)\s*Ft',
                    'i'
                ))[1], ''), ' ', ''), ',', '.'),
                '[^0-9.]',
                '',
                'g'
            ), '')::numeric,
            nullif(regexp_replace(
                replace(replace(coalesce((regexp_match(
                    i.note,
                    '[öo]sszeg\s*:?\s*([0-9\s.,]+)\s*Ft',
                    'i'
                ))[1], ''), ' ', ''), ',', '.'),
                '[^0-9.]',
                '',
                'g'
            ), '')::numeric,
            0
        ) as invoice_amount_huf
    from invoice_documents i
    where i.rn = 1
),
monthly_closure as (
    select *
    from (
        select
            c.courier_id,
            c.period_start::date as document_month,
            c.invoice_number as closure_invoice_number,
            c.payable_huf as closure_payable_huf,
            c.closed_at,
            row_number() over (
                partition by c.courier_id, c.period_start::date
                order by c.closed_at desc, c.updated_at desc, c.id desc
            ) as rn
        from settlement.courier_monthly_closure c
        where c.status = 'done'
    ) ranked
    where rn = 1
),
settlement_summary as (
    select *
    from (
        select
            coalesce(nullif(s.courier_id, ''), 'name:' || lower(trim(s.driver_name))) as courier_id,
            date_trunc('month', s.period_start::date)::date as document_month,
            s.payable_huf as summary_payable_huf,
            row_number() over (
                partition by coalesce(nullif(s.courier_id, ''), 'name:' || lower(trim(s.driver_name))), date_trunc('month', s.period_start::date)::date
                order by s.calculated_at desc, s.id desc
            ) as rn
        from settlement.courier_settlement_summary s
    ) ranked
    where rn = 1
)
select
    p.courier_id,
    p.courier_name,
    p.document_month,
    coalesce(nullif(i.invoice_number, ''), nullif(c.closure_invoice_number, ''), '') as invoice_number,
    coalesce(
        nullif(i.invoice_amount_huf, 0),
        nullif(p.paid_amount_huf, 0),
        nullif(c.closure_payable_huf, 0),
        nullif(ss.summary_payable_huf, 0),
        0
    ) as invoice_amount_huf,
    p.paid_amount_huf,
    c.closure_payable_huf,
    ss.summary_payable_huf,
    case
        when coalesce(i.invoice_amount_huf, 0) <> 0 then 'invoice_note'
        when coalesce(p.paid_amount_huf, 0) <> 0 then 'payment_status_note'
        when coalesce(c.closure_payable_huf, 0) <> 0 then 'monthly_closure'
        when coalesce(ss.summary_payable_huf, 0) <> 0 then 'settlement_summary'
        else 'missing'
    end as amount_source,
    p.status_note,
    p.payment_updated_at,
    p.payment_updated_by,
    i.invoice_document_id,
    i.invoice_title,
    i.invoice_file_name,
    i.invoice_note,
    i.invoice_uploaded_at,
    i.invoice_uploaded_by
from latest_paid p
left join latest_invoice i
  on i.courier_id = p.courier_id
 and i.document_month = p.document_month
left join monthly_closure c
  on c.courier_id = p.courier_id
 and c.document_month = p.document_month
left join settlement_summary ss
  on ss.courier_id = p.courier_id
 and ss.document_month = p.document_month;

grant select on settlement.vw_legacy_paid_invoice_dedup to service_role;
grant select on settlement.vw_legacy_paid_invoice_dedup to authenticated;

notify pgrst, 'reload schema';
