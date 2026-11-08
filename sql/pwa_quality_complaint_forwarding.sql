-- After pwa_quality_complaint_management.sql. No existing complaint or financial data is rewritten.
begin;
create table if not exists public.pwa_quality_complaint_deliveries (
 complaint_id uuid primary key references public.pwa_quality_complaints(id),
 payload jsonb not null,
 state text not null check (state in ('queued','processing','login_required','failed','uncertain','prepared','sent')),
 approved_by text not null,
 approved_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 lease_token uuid,
 lease_until timestamptz,
 submit_started_at timestamptz,
 confirmation text not null default '',
 last_error text not null default ''
);
alter table public.pwa_quality_complaint_deliveries drop constraint if exists pwa_quality_complaint_deliveries_state_check;
alter table public.pwa_quality_complaint_deliveries add constraint pwa_quality_complaint_deliveries_state_check check (state in ('queued','processing','login_required','failed','uncertain','prepared','sent'));
alter table public.pwa_quality_complaint_deliveries enable row level security;
revoke all on public.pwa_quality_complaint_deliveries from public, anon, authenticated;
grant select, insert, update on public.pwa_quality_complaint_deliveries to service_role;

create or replace function public.pwa_approve_quality_delivery(p_id uuid,p_actor text,p_payload jsonb)
returns setof public.pwa_quality_complaint_deliveries language plpgsql security invoker set search_path=public as $$
declare c public.pwa_quality_complaints; d public.pwa_quality_complaint_deliveries;
begin
 select * into c from public.pwa_quality_complaints where id=p_id for update;
 if not found or c.status <> 'open' then raise exception 'Only open complaints can be approved'; end if;
 select * into d from public.pwa_quality_complaint_deliveries where complaint_id=p_id for update;
 if found and d.state not in ('failed','login_required') then return next d; return; end if;
 if p_payload->>'complaint_id' is distinct from p_id::text then raise exception 'Invalid complaint payload'; end if;
 return query insert into public.pwa_quality_complaint_deliveries(complaint_id,payload,state,approved_by)
 values(p_id,p_payload,'queued',p_actor)
 on conflict(complaint_id) do update set payload=excluded.payload,state='queued',approved_by=p_actor,
 approved_at=now(),updated_at=now(),lease_token=null,lease_until=null,submit_started_at=null,last_error='',confirmation=''
 returning *;
end $$;

create or replace function public.pwa_claim_quality_delivery()
returns setof public.pwa_quality_complaint_deliveries language plpgsql security invoker set search_path=public as $$
begin
 update public.pwa_quality_complaint_deliveries set state=case when submit_started_at is null then 'queued' else 'uncertain' end,
 last_error='A robot munkamenete megszakadt.',updated_at=now()
 where state='processing' and lease_until < now();
 return query update public.pwa_quality_complaint_deliveries set state='processing',lease_token=gen_random_uuid(),
 lease_until=now()+interval '15 minutes',updated_at=now()
 where complaint_id=(select d.complaint_id from public.pwa_quality_complaint_deliveries d
 join public.pwa_quality_complaints c on c.id=d.complaint_id where d.state='queued' and c.status='open'
 order by d.approved_at for update of d skip locked limit 1) returning *;
end $$;

create or replace function public.pwa_start_quality_submission(p_id uuid,p_token uuid)
returns setof public.pwa_quality_complaint_deliveries language plpgsql security invoker set search_path=public as $$
begin
 return query update public.pwa_quality_complaint_deliveries set submit_started_at=now(),updated_at=now()
 where complaint_id=p_id and state='processing' and lease_token=p_token and lease_until>now() and submit_started_at is null returning *;
end $$;

create or replace function public.pwa_finish_quality_delivery(p_id uuid,p_token uuid,p_state text,p_confirmation text default '')
returns setof public.pwa_quality_complaint_deliveries language plpgsql security invoker set search_path=public as $$
declare d public.pwa_quality_complaint_deliveries;
begin
 -- Same lock order as admin approval. The worker can only prepare, never forward.
 perform 1 from public.pwa_quality_complaints where id=p_id for update;
 select * into d from public.pwa_quality_complaint_deliveries where complaint_id=p_id for update;
 if not found or d.lease_token is distinct from p_token then raise exception 'Invalid worker lease'; end if;
 if d.state <> 'processing' or p_state not in ('login_required','failed','uncertain','prepared') then raise exception 'Invalid transition'; end if;
 if d.submit_started_at is not null and p_state='failed' then raise exception 'Submission may have happened'; end if;
 if p_state='prepared' and d.submit_started_at is null then raise exception 'Preparation journal required'; end if;
 update public.pwa_quality_complaint_deliveries set state=p_state,updated_at=now(),
 confirmation='',
 last_error=case p_state when 'login_required' then 'Google-bejelentkezés szükséges.' when 'failed' then 'A kitöltés nem sikerült; beküldés nem indult.'
 when 'uncertain' then 'A beküldés eredménye nem igazolható. Ellenőrizd a Google-űrlap válaszai között; ne küldd be újra automatikusan.' else '' end
 where complaint_id=p_id;

 return query select * from public.pwa_quality_complaint_deliveries where complaint_id=p_id;
end $$;

-- Prevent a second preparation while the first one is queued/in flight.
create or replace function public.pwa_quality_delivery_guard() returns trigger
language plpgsql security invoker set search_path=public as $$
declare s text;
begin
 if new.status is distinct from old.status then
  select state into s from public.pwa_quality_complaint_deliveries where complaint_id=old.id;
  if s in ('queued','processing') then raise exception 'Automatic submission pending';end if;
  if new.status='closed' and s='uncertain' then raise exception 'Verify external submission first';end if;
  if new.status='forwarded' and s in ('uncertain','prepared') then
   update public.pwa_quality_complaint_deliveries set state='sent',confirmation=new.forwarding_reference,updated_at=now(),last_error=''
   where complaint_id=old.id;
  end if;
 end if;
 return new;
end $$;
drop trigger if exists pwa_quality_delivery_guard on public.pwa_quality_complaints;
create trigger pwa_quality_delivery_guard before update of status on public.pwa_quality_complaints for each row execute function public.pwa_quality_delivery_guard();
revoke all on function public.pwa_approve_quality_delivery(uuid,text,jsonb),public.pwa_claim_quality_delivery(),public.pwa_start_quality_submission(uuid,uuid),public.pwa_finish_quality_delivery(uuid,uuid,text,text),public.pwa_quality_delivery_guard() from public,anon,authenticated;
grant execute on function public.pwa_approve_quality_delivery(uuid,text,jsonb),public.pwa_claim_quality_delivery(),public.pwa_start_quality_submission(uuid,uuid),public.pwa_finish_quality_delivery(uuid,uuid,text,text),public.pwa_quality_delivery_guard() to service_role;
notify pgrst,'reload schema';
commit;
