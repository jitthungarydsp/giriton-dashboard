begin;

create schema if not exists settlement;

drop view if exists settlement.vw_invoice_discrepancy_list;

create or replace view settlement.vw_invoice_discrepancy_list as
with latest_snapshots as (
    select *
    from (
        select
            s.*,
            row_number() over (
                partition by s.courier_id, s.period_start::date
                order by s.version desc, s.created_at desc, s.id desc
            ) as rn
        from settlement.courier_finance_snapshot s
    ) ranked
    where rn = 1
),
snapshot_tig as (
    select
        s.id as snapshot_id,
        s.courier_id,
        s.courier_name,
        s.period_start::date as period_start,
        s.version as snapshot_version,
        s.created_at as snapshot_created_at,
        src.payload as tig_breakdown,
        coalesce(
            nullif(regexp_replace(coalesce(src.payload ->> 'finalTotalHuf', ''), '[^0-9.-]', '', 'g'), '')::numeric,
            nullif(regexp_replace(coalesce(s.metadata ->> 'tig_final_total', ''), '[^0-9.-]', '', 'g'), '')::numeric,
            0
        ) as transfer_expected_huf,
        coalesce(
            nullif(regexp_replace(coalesce(src.payload ->> 'cashGrossHuf', ''), '[^0-9.-]', '', 'g'), '')::numeric,
            0
        ) as cash_expected_huf
    from latest_snapshots s
    left join settlement.courier_finance_snapshot_source src
      on src.snapshot_id = s.id
     and src.source_key = 'tig_breakdown'
),
settlement_months as (
    select distinct
        coalesce(nullif(s.courier_id, ''), 'name:' || lower(trim(s.driver_name))) as courier_id,
        s.driver_name as courier_name,
        date_trunc('month', s.period_start::date)::date as period_start
    from settlement.courier_settlement_summary s
    where s.period_start is not null
),
base_months as (
    select
        st.courier_id,
        st.courier_name,
        st.period_start
    from snapshot_tig st

    union

    select
        sm.courier_id,
        sm.courier_name,
        sm.period_start
    from settlement_months sm
),
invoice_documents as (
    select
        d.id::text as invoice_document_id,
        d.courier_id,
        d.courier_name,
        date_trunc('month', d.document_month::date)::date as period_start,
        case
            when lower(coalesce(d.title, '')) like 'kp %'
              or lower(coalesce(d.title, '')) like '%kp szamla%'
              or lower(coalesce(d.title, '')) like '%kp számla%'
              or lower(coalesce(d.file_name, '')) like '%kp_szamla%'
              or lower(coalesce(d.file_name, '')) like '%kp-szamla%'
              or lower(coalesce(d.file_name, '')) like '%kp számla%'
              or lower(coalesce(d.note, '')) like '%fizetesi mod: kp%'
              or lower(coalesce(d.note, '')) like '%fizetési mód: kp%'
            then 'cash'
            else 'transfer'
        end as invoice_kind,
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
        ) as invoice_number,
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
        ) as invoice_amount_huf,
        d.title as invoice_title,
        d.file_name as invoice_file_name,
        d.note as invoice_note,
        d.uploaded_at as invoice_uploaded_at,
        d.uploaded_by as invoice_uploaded_by,
        row_number() over (
            partition by d.courier_id, date_trunc('month', d.document_month::date)::date,
            case
                when lower(coalesce(d.title, '')) like 'kp %'
                  or lower(coalesce(d.title, '')) like '%kp szamla%'
                  or lower(coalesce(d.title, '')) like '%kp számla%'
                  or lower(coalesce(d.file_name, '')) like '%kp_szamla%'
                  or lower(coalesce(d.file_name, '')) like '%kp-szamla%'
                  or lower(coalesce(d.file_name, '')) like '%kp számla%'
                  or lower(coalesce(d.note, '')) like '%fizetesi mod: kp%'
                  or lower(coalesce(d.note, '')) like '%fizetési mód: kp%'
                then 'cash'
                else 'transfer'
            end
            order by d.uploaded_at desc, d.id desc
        ) as rn
    from public.peopleforce_documents d
    where lower(coalesce(d.document_type, '')) = 'invoice'
       or lower(concat_ws(' ', d.document_type, d.title, d.file_name)) like '%szamla%'
       or lower(concat_ws(' ', d.document_type, d.title, d.file_name)) like '%számla%'
),
latest_invoices as (
    select *
    from invoice_documents
    where rn = 1
),
expected_invoice_rows as (
    select
        b.courier_id,
        coalesce(st.courier_name, b.courier_name) as courier_name,
        b.period_start,
        'transfer'::text as invoice_kind,
        'Atutalasos szamla'::text as invoice_kind_label,
        coalesce(st.transfer_expected_huf, 0) as expected_amount_huf,
        st.cash_expected_huf,
        st.snapshot_id,
        st.snapshot_version,
        st.snapshot_created_at,
        st.tig_breakdown
    from base_months b
    left join snapshot_tig st
      on st.courier_id = b.courier_id
     and st.period_start = b.period_start
    where coalesce(st.transfer_expected_huf, 0) > 0

    union all

    select
        b.courier_id,
        coalesce(st.courier_name, b.courier_name) as courier_name,
        b.period_start,
        'cash'::text as invoice_kind,
        'KP szamla'::text as invoice_kind_label,
        coalesce(st.cash_expected_huf, 0) as expected_amount_huf,
        st.cash_expected_huf,
        st.snapshot_id,
        st.snapshot_version,
        st.snapshot_created_at,
        st.tig_breakdown
    from base_months b
    left join snapshot_tig st
      on st.courier_id = b.courier_id
     and st.period_start = b.period_start
    where coalesce(st.cash_expected_huf, 0) > 0
),
compared as (
    select
        e.courier_id,
        e.courier_name,
        e.period_start,
        e.invoice_kind,
        e.invoice_kind_label,
        e.expected_amount_huf,
        coalesce(i.invoice_amount_huf, 0) as uploaded_invoice_amount_huf,
        coalesce(i.invoice_amount_huf, 0) - e.expected_amount_huf as difference_huf,
        i.invoice_document_id,
        i.invoice_number,
        i.invoice_title,
        i.invoice_file_name,
        i.invoice_note,
        i.invoice_uploaded_at,
        i.invoice_uploaded_by,
        e.snapshot_id,
        e.snapshot_version,
        e.snapshot_created_at,
        e.tig_breakdown,
        case
            when i.invoice_document_id is null and e.invoice_kind = 'cash' then 'missing_cash_invoice'
            when i.invoice_document_id is null then 'missing_transfer_invoice'
            when coalesce(i.invoice_amount_huf, 0) = 0 then 'invoice_amount_not_read'
            when abs(coalesce(i.invoice_amount_huf, 0) - e.expected_amount_huf) > 1 then 'amount_difference'
            else 'ok'
        end as issue_type
    from expected_invoice_rows e
    left join latest_invoices i
      on i.courier_id = e.courier_id
     and i.period_start = e.period_start
     and i.invoice_kind = e.invoice_kind
)
select
    courier_id,
    courier_name,
    period_start,
    invoice_kind,
    invoice_kind_label,
    issue_type,
    expected_amount_huf,
    uploaded_invoice_amount_huf,
    difference_huf,
    invoice_number,
    invoice_document_id,
    invoice_title,
    invoice_file_name,
    invoice_uploaded_at,
    invoice_uploaded_by,
    snapshot_id,
    snapshot_version,
    snapshot_created_at,
    invoice_note,
    tig_breakdown
from compared
where issue_type <> 'ok'
order by
    period_start desc,
    courier_name nulls last,
    courier_id,
    case invoice_kind when 'transfer' then 1 else 2 end;

grant select on settlement.vw_invoice_discrepancy_list to service_role;
grant select on settlement.vw_invoice_discrepancy_list to authenticated;

notify pgrst, 'reload schema';

commit;
