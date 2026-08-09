begin;

alter table settlement.cfg_jitt_periodic_fees
    drop constraint if exists cfg_jitt_periodic_fees_condition_metric_check;

alter table settlement.cfg_jitt_periodic_fees
    add constraint cfg_jitt_periodic_fees_condition_metric_check
    check (
        condition_metric in (
            'none',
            'orders_per_route',
            'routes_per_day',
            'routes_in_period',
            'orders_in_period',
            'every_n_routes_per_day',
            'every_n_routes_in_period',
            'orders_over_threshold_every_n_per_route'
        )
    );

commit;
