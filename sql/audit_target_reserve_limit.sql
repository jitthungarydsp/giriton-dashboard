-- Csak olvasó ellenőrzés a mentett havi céltartalék-számításokon.
-- A NULL dátumokkal minden hónapot vizsgál. Egy hónaphoz például mindkét
-- dátumot állítsd '2026-09-01'-re. A lezárt hónapok is láthatók maradnak.
-- A kézi kifizetéseket/jóváírásokat visszaadjuk a nettó havi változáshoz,
-- így ezek nem fedik el az ugyanabban a hónapban történt túlvonást.
-- Nem módosít adatot, és nem indít újraszámítást.
with filters as (
    select null::date as first_month,
           null::date as last_month
), checked as (
    select
        m.*,
        coalesce(s.courier_name, names.courier_name, m.courier_id) as courier_name,
        s.id as snapshot_id,
        s.version as snapshot_version,
        s.source as snapshot_source,
        s.metadata as snapshot_metadata,
        r.id as parameter_id,
        r.valid_from as parameter_valid_from,
        coalesce(r.base_insurance_total_huf, 350000)::numeric as balance_target,
        -- Ez az oszlop régebbi DB-sémákból még hiányozhat.
        coalesce((to_jsonb(r)->>'reserve_target_huf')::numeric, 50000) as monthly_limit,
        coalesce(e.released_huf, 0) as released_huf,
        greatest(m.reserve_addition_huf + coalesce(e.released_huf, 0), 0) as actual_topup
    from settlement.courier_target_reserve_monthly m
    cross join filters f
    left join lateral (
        select rule.*
        from settlement.cfg_jitt_reserve_insurance_rules rule
        where rule.is_active = true
          and rule.deleted_at is null
          and rule.valid_from <= m.period_start
          and (rule.valid_to is null or rule.valid_to >= m.period_start)
        order by rule.priority asc, rule.valid_from desc, rule.id
        limit 1
    ) r on true
    left join lateral (
        select sum(event.amount_huf) as released_huf
        from settlement.courier_target_reserve_event event
        where event.courier_id = m.courier_id
          and event.period_start = m.period_start
          and event.event_type in ('payment', 'deduction')
          and event.deleted_at is null
    ) e on true
    left join lateral (
        select snap.id, snap.courier_name, snap.version, snap.source, snap.metadata
        from settlement.courier_finance_snapshot snap
        where snap.courier_id = m.courier_id
          and snap.period_start = m.period_start
        order by snap.version desc, snap.created_at desc, snap.id desc
        limit 1
    ) s on true
    left join (
        select courier_id::text as courier_id, max(courier_name) as courier_name
        from public.courier_master
        group by courier_id::text
    ) names on names.courier_id = m.courier_id
    where (f.first_month is null or m.period_start >= f.first_month)
      and (f.last_month is null or m.period_start <= f.last_month)
), limits as (
    select checked.*,
           least(monthly_limit, greatest(balance_target - reserve_before_huf, 0))
               as allowed_topup_max
    from checked
), errors as (
    select limits.*,
           actual_topup - allowed_topup_max as excess_huf
    from limits
    where actual_topup > allowed_topup_max
)
select
    to_char(period_start, 'YYYY-MM') as "Hónap",
    courier_id as "Futár ID",
    courier_name as "Futár",
    case when reserve_before_huf >= balance_target
         then 'A nyitó egyenleg már elérte a célösszeget'
         when actual_topup > greatest(balance_target - reserve_before_huf, 0)
         then 'A havi feltöltés túllépte a célösszeget'
         else 'A havi feltöltés túllépte a havi maximumot'
    end as "Hiba",
    reserve_before_huf as "Nyitó CT (Ft)",
    balance_target as "Paraméter szerinti célösszeg (Ft)",
    monthly_limit as "Havi maximum (Ft)",
    actual_topup as "Tényleges CT-feltöltés (Ft)",
    allowed_topup_max as "Megengedett feltöltés maximuma (Ft)",
    released_huf as "Kézi CT-kifizetés és jóváírás (Ft)",
    excess_huf as "Túlvonás (Ft)",
    insurance_fee_huf as "Biztosítás (Ft)",
    reserve_after_huf as "Mentett záró CT (Ft)",
    reserve_after_huf - excess_huf as "Záró CT a túlvonás nélkül (Ft)",
    payable_after_insurance_huf as "Mentett kifizetendő (Ft)",
    payable_after_insurance_huf + excess_huf as "Kifizetendő a túlvonás nélkül (Ft)",
    case when reserve_after_huf - excess_huf >= balance_target then 'Done'
         else 'In progress' end as "CT státusz a túlvonás nélkül",
    status as "Havi elszámolás állapota",
    snapshot_version as "Legutóbbi pénzügyi verzió",
    snapshot_source as "Pénzügyi verzió forrása",
    case when coalesce(snapshot_metadata->>'restored_from_snapshot_id', '') <> ''
         then 'Visszaállított verzió: külön ellenőrzendő'
         when snapshot_metadata->>'reserve_release_booked' = 'true'
         then 'Kézi CT-művelet már könyvelve'
         else '' end as "Ellenőrzési megjegyzés",
    snapshot_id as "Snapshot ID",
    parameter_id as "Paraméter ID",
    parameter_valid_from as "Paraméter érvényes ettől",
    case when parameter_id is null then 'Alapértékek: nincs aktív havi paraméterszabály'
         else 'A hónapra érvényes paraméterszabály' end as "Paraméter forrása"
from errors
order by period_start desc, excess_huf desc, courier_name, courier_id;
