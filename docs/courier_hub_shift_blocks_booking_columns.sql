alter table public.courier_hub_shift_blocks_raw
    add column if not exists kifli_booking text,
    add column if not exists muszakpro_booking text;

create or replace view public.vw_courier_hub_shift_block_capacity as
select
    work_date,
    warehouse_id,
    warehouse_code,
    dsp_id,
    block_key,
    shift_template_id,
    template_name,
    slot_from,
    slot_to,
    occupancy_from,
    occupancy_to,
    status,
    assigned,
    opened,
    free_slots,
    kifli_booking,
    muszakpro_booking,
    capacity_published,
    fetched_at,
    updated_at
from public.courier_hub_shift_blocks_raw;

notify pgrst, 'reload schema';
