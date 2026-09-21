begin;

-- The roster sync stores one row per courier, warehouse, DSP and roster_date.
-- Older databases may still have the primary key on only courier_id, warehouse_id, dsp_id,
-- which blocks the next day's roster with duplicate-key errors.

delete from public.courier_hub_master old_row
using public.courier_hub_master keep_row
where old_row.ctid < keep_row.ctid
  and old_row.courier_id = keep_row.courier_id
  and old_row.warehouse_id = keep_row.warehouse_id
  and old_row.dsp_id = keep_row.dsp_id
  and old_row.roster_date = keep_row.roster_date
  and (
      keep_row.updated_at > old_row.updated_at
      or (
          keep_row.updated_at = old_row.updated_at
          and keep_row.fetched_at >= old_row.fetched_at
      )
  );

alter table public.courier_hub_master
    drop constraint if exists courier_hub_master_pkey;

alter table public.courier_hub_master
    add constraint courier_hub_master_pkey
    primary key (courier_id, warehouse_id, dsp_id, roster_date);

create unique index if not exists courier_hub_master_upsert_uidx
    on public.courier_hub_master (courier_id, warehouse_id, dsp_id, roster_date);

commit;
