with period as (
    select date '2026-09-01' as starts,
           date '2026-09-30' as ends
), courier_names as (
    select courier_id::text as courier_id, max(courier_name) as courier_name
    from public.courier_master
    group by courier_id::text
), rating_corrections as (
    select a.*,
           case when a.adjustment_type in ('correction_deduction', 'manual_correction_deduction')
                then -abs(a.amount_huf) else a.amount_huf end as signed_amount
    from settlement.courier_settlement_adjustment a
    cross join period p
    where a.is_active = true
      and a.deleted_at is null
      and a.adjustment_type in (
          'correction', 'manual_correction', 'correction_income',
          'correction_deduction', 'manual_correction_deduction'
      )
      and coalesce(a.valid_from, a.effective_date) <= p.ends
      and (a.valid_to is null or a.valid_to >= p.starts)
      and translate(lower(coalesce(a.note, '')), 'áéíóöőúüű', 'aeiooouuu')
          ~ 'ugyfel[[:space:]-]*ertekel|customer[[:space:]-]*rating'
)
select
    r.courier_id as "Futár ID",
    c.courier_name as "Futár",
    (regexp_match(
        translate(lower(coalesce(r.note, '')), 'áéíóöőúüű', 'aeiooouuu'),
        '([0-9]+)[[:space:]]*kor([[:space:]|,;.]|$)'
    ))[1]::integer as "Körök száma",
    r.signed_amount as "Ügyfélértékelési korrekció (Ft)",
    sum(r.signed_amount) over (partition by r.courier_id)
        as "Futár korrekciója összesen (Ft)",
    r.note as "Megjegyzés",
    coalesce(r.valid_from, r.effective_date) as "Érvényes ettől",
    r.valid_to as "Érvényes eddig",
    r.id as "Tétel ID"
from rating_corrections r
left join courier_names c on c.courier_id = r.courier_id::text
order by "Futár korrekciója összesen (Ft)" desc, "Futár", r.created_at, r.id;
