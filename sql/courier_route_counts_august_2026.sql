-- Read-only: August route counts from each courier's latest saved settlement.
-- Repeated imports are not added together.
with latest as (
    select distinct on (courier_id)
        courier_id, driver_name, route_count, order_count, calculated_at
    from settlement.courier_settlement_summary
    where period_start >= date '2026-08-01'
      and period_start < date '2026-09-01'
      and nullif(courier_id, '') is not null
    order by courier_id, calculated_at desc nulls last, session_id desc
)
select
    courier_id as "Futár ID",
    driver_name as "Futár",
    coalesce(route_count, 0) as "Kifutott körök",
    coalesce(order_count, 0) as "Rendelések",
    calculated_at as "Összesítés mentve"
from latest
order by "Kifutott körök" desc, "Futár";
