alter table public.mart_dsp_route_stories
    add column if not exists available_at timestamp,
    add column if not exists queue_started_at timestamp,
    add column if not exists total_route_minutes integer,
    add column if not exists gps_distance_km numeric(10,3),
    add column if not exists checkpoint_straight_km numeric(10,3),
    add column if not exists booking_shift_count integer not null default 0,
    add column if not exists next_booking_shift_text text,
    add column if not exists next_booking_shift_start timestamp,
    add column if not exists next_shift_delay_minutes integer;

notify pgrst, 'reload schema';
