begin;

-- Required by scripts/sync_courier_hub_master.py:
-- upsert on_conflict=courier_id,warehouse_id,dsp_id,roster_date.
-- Keep the freshest row if an older table already contains duplicates.
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

create unique index if not exists courier_hub_master_upsert_uidx
    on public.courier_hub_master (courier_id, warehouse_id, dsp_id, roster_date);

commit;
