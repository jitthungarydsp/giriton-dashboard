alter table settlement.cfg_jitt_customer_rating_rules
    add column if not exists route_type text not null default 'normal'
    check (route_type in ('normal', 'express', 'regional', 'any'));

insert into settlement.cfg_jitt_customer_rating_rules (
    level_code,
    route_type,
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
    source.route_type,
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
        ('Customer rating normal 4.90-5.00', 'normal', 4.90::numeric, 5.00::numeric, 500::integer, date '2026-05-01', null::date, 1::integer, 'Customer rating bonus: 4.90-5.00 average gives 500 HUF per normal route'),
        ('Customer rating normal 4.80-4.89', 'normal', 4.80::numeric, 4.89::numeric, 300::integer, date '2026-05-01', null::date, 2::integer, 'Customer rating bonus: 4.80-4.89 average gives 300 HUF per normal route'),
        ('Customer rating normal 4.70-4.79', 'normal', 4.70::numeric, 4.79::numeric, 150::integer, date '2026-05-01', null::date, 3::integer, 'Customer rating bonus: 4.70-4.79 average gives 150 HUF per normal route'),
        ('Customer rating express 4.90-5.00', 'express', 4.90::numeric, 5.00::numeric, 500::integer, date '2026-05-01', null::date, 1::integer, 'Customer rating bonus: 4.90-5.00 average gives 500 HUF per express route'),
        ('Customer rating express 4.80-4.89', 'express', 4.80::numeric, 4.89::numeric, 300::integer, date '2026-05-01', null::date, 2::integer, 'Customer rating bonus: 4.80-4.89 average gives 300 HUF per express route'),
        ('Customer rating express 4.70-4.79', 'express', 4.70::numeric, 4.79::numeric, 150::integer, date '2026-05-01', null::date, 3::integer, 'Customer rating bonus: 4.70-4.79 average gives 150 HUF per express route')
) as source(level_code, route_type, rating_min_value, rating_max_value, courier_amount_huf, valid_from, valid_to, priority, note)
where not exists (
    select 1
    from settlement.cfg_jitt_customer_rating_rules target
    where target.level_code = source.level_code
      and target.route_type = source.route_type
      and target.valid_from = source.valid_from
      and target.deleted_at is null
);

notify pgrst, 'reload schema';
