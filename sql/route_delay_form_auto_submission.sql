-- Apply after route_delay_form_drafts.sql. Existing rows remain unchanged.
begin;
alter table settlement.route_delay_form_draft
 drop constraint if exists route_delay_form_draft_state_check;
alter table settlement.route_delay_form_draft
 add constraint route_delay_form_draft_state_check
 check (state in ('draft','prepared','queued','processing','uncertain','sent'));
create or replace function settlement.queue_route_delay_form_batch(p_records jsonb,p_actor text)
returns integer language plpgsql security invoker set search_path=settlement,pg_temp as $$
declare expected_count integer; changed_count integer;
begin
 perform pg_advisory_xact_lock(658143920);
 if exists(select 1 from settlement.route_delay_form_draft where state in ('queued','processing','uncertain')) then
  raise exception 'A submission is pending or requires verification';
 end if;
 if jsonb_typeof(p_records) <> 'array' or jsonb_array_length(p_records)=0 then
  raise exception 'No records supplied';
 end if;
 expected_count := jsonb_array_length(p_records);
 -- All-or-nothing CAS: one stale/already-sent row rolls the entire batch back.
 update settlement.route_delay_form_draft d set state='queued',confirmation='',
  updated_by=p_actor,updated_at=clock_timestamp()
 from jsonb_to_recordset(p_records) as r(id uuid,content_hash text,updated_at timestamptz)
 where d.id=r.id and d.state='prepared' and d.content_hash=r.content_hash and d.updated_at=r.updated_at;
 get diagnostics changed_count = row_count;
 if changed_count <> expected_count then
  raise exception 'The complaint list changed; reload before submitting';
 end if;
 return changed_count;
end;
$$;
revoke all on function settlement.queue_route_delay_form_batch(jsonb,text) from public,anon,authenticated;
grant execute on function settlement.queue_route_delay_form_batch(jsonb,text) to service_role;
commit;
