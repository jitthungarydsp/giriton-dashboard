-- READ ONLY: gather evidence before restoring Magyar Csilla's reserve/finance.
-- Today means 2026-10-19 in Europe/Budapest; settlement month is September.
with today_events as (
    select * from settlement.courier_target_reserve_event
    where courier_id = '6686'
      and created_at >= (timestamp '2026-10-19 00:00:00' at time zone 'Europe/Budapest')
      and created_at < (timestamp '2026-10-20 00:00:00' at time zone 'Europe/Budapest')
), cutoff as (
    select coalesce(min(created_at), timestamp '2026-10-19 00:00:00' at time zone 'Europe/Budapest') as happened_at
    from today_events
), previous_snapshot as (
    select s.* from settlement.courier_finance_snapshot s, cutoff c
    where s.courier_id = '6686' and s.period_start = date '2026-09-01'
      and s.created_at < c.happened_at
    order by s.version desc, s.created_at desc limit 1
)
select jsonb_build_object(
    'courier_id', '6686',
    'today_events', (select coalesce(jsonb_agg(to_jsonb(e) order by e.created_at), '[]') from today_events e),
    'september_events', (select coalesce(jsonb_agg(to_jsonb(e) order by e.created_at), '[]')
        from settlement.courier_target_reserve_event e
        where e.courier_id = '6686' and e.period_start = date '2026-09-01'),
    'current_reserve', (select coalesce(jsonb_agg(to_jsonb(r)), '[]')
        from public.courier_target_reserve r where r."courier_ID"::text = '6686'),
    'monthly_reserve', (select coalesce(jsonb_agg(to_jsonb(m) order by m.period_start), '[]')
        from settlement.courier_target_reserve_monthly m
        where m.courier_id = '6686' and m.period_start >= date '2026-08-01'),
    'snapshot_before_first_event', (select to_jsonb(s) from previous_snapshot s),
    'items_before_first_event', (select coalesce(jsonb_agg(to_jsonb(i)), '[]')
        from settlement.courier_finance_snapshot_item i
        where i.snapshot_id in (select id from previous_snapshot)),
    'sources_before_first_event', (select coalesce(jsonb_agg(to_jsonb(s)), '[]')
        from settlement.courier_finance_snapshot_source s
        where s.snapshot_id in (select id from previous_snapshot)
          and s.source_key in ('target_reserve_month', 'working_row', 'settlement_summary')),
    'september_snapshot_history', (select coalesce(jsonb_agg(to_jsonb(s) order by s.version), '[]')
        from settlement.courier_finance_snapshot s
        where s.courier_id = '6686' and s.period_start = date '2026-09-01'),
    'monthly_closures', (select coalesce(jsonb_agg(to_jsonb(c)), '[]')
        from settlement.courier_monthly_closure c
        where c.courier_id = '6686' and c.period_start = date '2026-09-01')
) as restoration_audit;
