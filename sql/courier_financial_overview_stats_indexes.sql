begin;

create index if not exists courier_financial_overview_delay_courier_date_idx
    on public.courier_financial_overview_delay (courier_id, delivery_date, route_id)
    include (
        warehouse_id,
        route_order_count,
        stops_count,
        delayed_stops_count,
        total_delay_minutes,
        max_delay_minutes,
        slot_miss_projected_count,
        rejected_stops_count
    );

create index if not exists courier_financial_overview_compliance_courier_date_idx
    on public.courier_financial_overview_compliance (courier_id, shift_date, route_id)
    include (
        warehouse_id,
        planned_start_at,
        actual_start_at,
        route_assigned_at,
        shift_available_at,
        planned_departure_at,
        departed_at,
        last_order_finished_at,
        warehouse_arrived_at,
        vehicle_plate,
        planned_start_delay_minutes,
        departure_delay_minutes,
        return_delay_minutes
    );

commit;

notify pgrst, 'reload schema';
