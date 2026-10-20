-- Install only: creates a durable per-courier/month queue and atomic publisher.
-- Does not run the session-wide route calculator or alter any parameters/PDFs.
begin;
create table if not exists settlement.bonus_malus_refresh_queue (
 courier_id text not null, period_start date not null,
 revision bigint not null default 1, state text not null default 'pending',
 updated_at timestamptz not null default now(), last_error text,
 primary key(courier_id,period_start),
 check(period_start = date_trunc('month',period_start)::date),
 check(state in ('pending','error','done','protected','missing_snapshot'))
);
alter table settlement.bonus_malus_refresh_queue enable row level security;
revoke all on settlement.bonus_malus_refresh_queue from public,anon,authenticated;
grant select,insert,update,delete on settlement.bonus_malus_refresh_queue to service_role;

create or replace function settlement.queue_bonus_malus_refresh()
returns trigger language plpgsql security definer set search_path=pg_catalog as $$
declare r jsonb; v_start date; v_end date; v_month date; v_courier text;
begin
 if tg_op='UPDATE' and
   (to_jsonb(old)-array['updated_at','updated_by']) = (to_jsonb(new)-array['updated_at','updated_by']) then
   return new;
 end if;
 for r in select value from jsonb_array_elements(
   case tg_op when 'INSERT' then jsonb_build_array(to_jsonb(new))
              when 'DELETE' then jsonb_build_array(to_jsonb(old))
              else jsonb_build_array(to_jsonb(old),to_jsonb(new)) end)
 loop
   if r->>'adjustment_type' not in ('bonus','malus') then continue; end if;
   v_courier := r->>'courier_id';
   v_start := coalesce(nullif(r->>'valid_from','')::date,nullif(r->>'effective_date','')::date);
   v_end := coalesce(nullif(r->>'valid_to','')::date,'infinity'::date);
   if v_start is null or nullif(v_courier,'') is null then continue; end if;
   -- Both old and new periods are queued when a transaction moves month/courier.
   for v_month in
     select date_trunc('month',v_start)::date
     union select distinct period_start from settlement.courier_finance_snapshot
      where courier_id=v_courier and period_start<=v_end
      and period_start + interval '1 month' > v_start
   loop
     insert into settlement.bonus_malus_refresh_queue(courier_id,period_start)
     values(v_courier,v_month)
     on conflict(courier_id,period_start) do update
      set revision=bonus_malus_refresh_queue.revision+1,state='pending',updated_at=now(),last_error=null;
   end loop;
 end loop;
 if tg_op='DELETE' then return old; end if;
 return new;
end $$;
drop trigger if exists queue_bonus_malus_refresh on settlement.courier_settlement_adjustment;
create trigger queue_bonus_malus_refresh after insert or update or delete
 on settlement.courier_settlement_adjustment for each row
 execute function settlement.queue_bonus_malus_refresh();

create or replace function settlement.resume_missing_bonus_malus_snapshot()
returns trigger language plpgsql security definer set search_path=pg_catalog as $$
begin
 update settlement.bonus_malus_refresh_queue set state='pending',revision=revision+1,updated_at=now(),last_error=null
  where courier_id=new.courier_id and period_start=new.period_start and state='missing_snapshot';
 return new;
end $$;
drop trigger if exists resume_missing_bonus_malus_snapshot on settlement.courier_finance_snapshot;
create trigger resume_missing_bonus_malus_snapshot after insert on settlement.courier_finance_snapshot
 for each row execute function settlement.resume_missing_bonus_malus_snapshot();
revoke all on function settlement.resume_missing_bonus_malus_snapshot() from public,anon,authenticated;

create or replace function settlement.publish_bonus_malus_refresh(
 p_courier_id text,p_period_start date,p_revision bigint,p_base_snapshot_id uuid,
 p_fingerprint text,p_prepared jsonb
) returns jsonb language plpgsql security invoker set search_path=pg_catalog as $$
declare q settlement.bonus_malus_refresh_queue%rowtype;
 s settlement.courier_finance_snapshot%rowtype; v_id uuid;
 total numeric; income numeric; deductions numeric; correction numeric; tig numeric;
begin
 perform pg_advisory_xact_lock(hashtextextended('pwa_monthly_payment:'||p_courier_id||':'||p_period_start,0));
 select * into q from settlement.bonus_malus_refresh_queue
  where courier_id=p_courier_id and period_start=p_period_start for update;
 if not found or q.revision<>p_revision then raise exception 'A forrástételek megváltoztak; újrapróbálás szükséges.'; end if;
 if exists(select 1 from settlement.courier_monthly_closure where courier_id=p_courier_id and period_start=p_period_start and status='done')
 or exists(select 1 from public.peopleforce_card_statuses where courier_id::text=p_courier_id
   and document_month=p_period_start and action_key='invoice_payment' and status='done') then
   update settlement.bonus_malus_refresh_queue set state='protected',last_error='Lezárt vagy kifizetett hónap; kézi felülvizsgálat szükséges.'
     where courier_id=p_courier_id and period_start=p_period_start;
   return jsonb_build_object('protected',true);
 end if;
 select * into s from settlement.courier_finance_snapshot where courier_id=p_courier_id
   and period_start=p_period_start order by version desc limit 1 for update;
 if not found then
   update settlement.bonus_malus_refresh_queue set state='missing_snapshot',last_error='Még nincs mentett havi elszámolás.'
    where courier_id=p_courier_id and period_start=p_period_start;
   return jsonb_build_object('missingSnapshot',true);
 end if;
 if s.id is distinct from p_base_snapshot_id then raise exception 'Az elszámolás verziója megváltozott.'; end if;
 if p_prepared is null then
   update settlement.bonus_malus_refresh_queue set state='done',last_error=null
    where courier_id=p_courier_id and period_start=p_period_start;
   return jsonb_build_object('unchanged',true,'version',s.version);
 end if;
 if p_prepared->'metadata'->>'source' is distinct from 'bonus_malus_refresh'
 or p_prepared->'metadata'->>'bonus_malus_base_snapshot_id' is distinct from s.id::text
 or nullif(p_fingerprint,'') is null
 or jsonb_typeof(p_prepared->'items') is distinct from 'array'
 or jsonb_typeof(p_prepared->'sources') is distinct from 'array' then
   raise exception 'Hiányos bónusz/malusz mentés.';
 end if;
 select (p_prepared->'metadata'->>'payable_total')::numeric,
        (p_prepared->'metadata'->>'income_total')::numeric,
        (p_prepared->'metadata'->>'deduction_total')::numeric,
        (p_prepared->'metadata'->>'correction_total')::numeric,
        (p_prepared->'metadata'->>'tig_final_total')::numeric
 into total,income,deductions,correction,tig;
 if total is null or income is null or deductions is null or correction is null or tig is null
 or total<>income+deductions+correction
 or (select count(*) from jsonb_array_elements(p_prepared->'items') i
     where i->>'section'='finance' and i->>'item_key'='payable' and (i->>'amount_value')::numeric=total)<>1
 or (select count(*) from jsonb_array_elements(p_prepared->'items') i
     where i->>'section'='tig' and i->>'item_key'='tig_final_total' and (i->>'amount_value')::numeric=tig)<>1
 or (select coalesce(sum((i->>'amount_value')::numeric),0) from jsonb_array_elements(p_prepared->'items') i
     where i->>'section'='tig' and i->>'item_key' not in ('tig_final_total','tig_cash_service'))<>tig then
   raise exception 'Az összesítések nem egyeznek.';
 end if;
 -- Reject accidental changes to base pay, route counts, corrections or reserve.
 if exists(select 1 from settlement.courier_finance_snapshot_item old_item
   where old_item.snapshot_id=s.id and old_item.section='finance'
    and old_item.item_key not in ('manual_bonus','manual_malus','bonus_malus','income','deductions','payable')
    and old_item.item_key not like 'jitt_bonus_%' and old_item.item_key not like 'jitt_malus_%'
    and not exists(select 1 from jsonb_array_elements(p_prepared->'items') i
      where i->>'section'='finance' and i->>'item_key'=old_item.item_key
       and (i->>'amount_value')::numeric=old_item.amount_value)) then
   raise exception 'A bónusz/malusz frissítés nem módosíthat más pénzügyi tételt.';
 end if;
 insert into settlement.courier_finance_snapshot
  (courier_id,courier_name,period_start,version,source,calculation_mode,warehouse_label,session_id,
   fingerprint,previous_snapshot_id,previous_fingerprint,changed_from_previous,metadata,created_by)
 values(p_courier_id,s.courier_name,p_period_start,s.version+1,'bonus_malus_refresh',s.calculation_mode,
  s.warehouse_label,s.session_id,p_fingerprint,s.id,s.fingerprint,true,p_prepared->'metadata','bonus-malus-refresh')
 returning id into v_id;
 insert into settlement.courier_finance_snapshot_item
  (snapshot_id,section,item_key,item_label,amount_value,amount_kind,note,display_order)
 select v_id,x.section,x.item_key,x.item_label,x.amount_value,x.amount_kind,x.note,x.display_order
 from jsonb_to_recordset(p_prepared->'items') as x(section text,item_key text,item_label text,
  amount_value numeric,amount_kind text,note text,display_order integer);
 insert into settlement.courier_finance_snapshot_source(snapshot_id,source_key,source_table,payload,row_count)
 select v_id,x.source_key,x.source_table,x.payload,x.row_count
 from jsonb_to_recordset(p_prepared->'sources') as x(source_key text,source_table text,payload jsonb,row_count integer);
 update settlement.bonus_malus_refresh_queue set state='done',last_error=null
  where courier_id=p_courier_id and period_start=p_period_start;
 return jsonb_build_object('ok',true,'snapshotId',v_id,'version',s.version+1,'payable',total);
end $$;
revoke all on function settlement.publish_bonus_malus_refresh(text,date,bigint,uuid,text,jsonb) from public,anon,authenticated;
grant execute on function settlement.publish_bonus_malus_refresh(text,date,bigint,uuid,text,jsonb) to service_role;
revoke all on function settlement.queue_bonus_malus_refresh() from public,anon,authenticated;

-- Recover imported-but-not-published rows (including changes from before install).
-- Enqueue only months with source changes after their latest saved version.
with latest as (
 select distinct on (courier_id,period_start) * from settlement.courier_finance_snapshot
 order by courier_id,period_start,version desc
)
insert into settlement.bonus_malus_refresh_queue(courier_id,period_start)
select distinct s.courier_id,s.period_start from latest s
join settlement.courier_settlement_adjustment a on a.courier_id=s.courier_id
 and a.adjustment_type in ('bonus','malus')
 and coalesce(a.valid_from,a.effective_date) < s.period_start+interval '1 month'
 and coalesce(a.valid_to,'infinity'::date)>=s.period_start
where greatest(a.created_at,a.updated_at,a.deleted_at)>s.created_at
on conflict(courier_id,period_start) do nothing;
notify pgrst,'reload schema';
commit;
