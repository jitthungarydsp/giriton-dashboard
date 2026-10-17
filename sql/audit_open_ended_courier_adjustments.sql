-- Read-only audit: active manual adjustments without an end date.
-- No rows are changed. Review whether each entry is one-off or recurring.
with courier_names as (
    select courier_id::text as courier_id, max(courier_name) as courier_name
    from public.courier_master
    group by courier_id::text
)
select
    a.id,
    a.courier_id as "Futár ID",
    c.courier_name as "Futár",
    a.adjustment_type as "Típus",
    a.amount_huf as "Összeg (Ft)",
    a.note as "Megjegyzés",
    coalesce(a.valid_from, a.effective_date) as "Érvényes ettől",
    a.valid_to as "Érvényes eddig",
    case
        when coalesce(a.valid_from, a.effective_date) <
             date_trunc('month', now() at time zone 'Europe/Budapest')::date
        then 'Korábbi hónaptól ismétlődhet'
        else 'Végdátum nélkül aktív'
    end as "Ellenőrzés",
    a.created_by as "Létrehozta",
    a.created_at as "Létrehozva"
from settlement.courier_settlement_adjustment a
left join courier_names c on c.courier_id = a.courier_id::text
where a.is_active = true
  and a.deleted_at is null
  and a.valid_to is null
order by coalesce(a.valid_from, a.effective_date), c.courier_name, a.id;
