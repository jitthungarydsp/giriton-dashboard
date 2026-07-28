insert into settlement.cfg_jitt_customer_rating_rules (
    level_code,
    rating_min_percent,
    rating_max_percent,
    courier_amount_huf,
    valid_from,
    valid_to,
    priority,
    is_active,
    note,
    created_by,
    updated_by,
    updated_at
)
select
    source.level_code,
    source.rating_min_value,
    source.rating_max_value,
    source.courier_amount_huf,
    source.valid_from,
    source.valid_to,
    source.priority,
    true,
    source.note,
    'seed',
    'seed',
    now()
from (
    values
        ('Customer rating 4.90-5.00', 4.90::numeric, 5.00::numeric, 500::integer, date '2026-05-01', null::date, 1::integer, 'Customer rating bonus: 4.90-5.00 average gives 500 HUF per route'),
        ('Customer rating 4.80-4.89', 4.80::numeric, 4.89::numeric, 300::integer, date '2026-05-01', null::date, 2::integer, 'Customer rating bonus: 4.80-4.89 average gives 300 HUF per route'),
        ('Customer rating 4.70-4.79', 4.70::numeric, 4.79::numeric, 150::integer, date '2026-05-01', null::date, 3::integer, 'Customer rating bonus: 4.70-4.79 average gives 150 HUF per route')
) as source(level_code, rating_min_value, rating_max_value, courier_amount_huf, valid_from, valid_to, priority, note)
where not exists (
    select 1
    from settlement.cfg_jitt_customer_rating_rules target
    where target.level_code = source.level_code
      and target.valid_from = source.valid_from
      and target.deleted_at is null
);

notify pgrst, 'reload schema';
