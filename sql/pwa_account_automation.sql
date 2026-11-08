-- Apply after pwa_users, pwa_registration_requests and pwa_password_reset_requests.
begin;
create table if not exists public.pwa_account_jobs (
 id uuid primary key default gen_random_uuid(), kind text not null check(kind in ('reset','registration')),
 request_id bigint not null, courier_id integer not null, email text not null, username text not null,
 state text not null default 'queued' check(state in ('queued','processing','sending','sent','manual','failed','uncertain')),
 actor text not null default 'automatic', note text not null default '',
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(kind,request_id)
);
create index if not exists pwa_account_jobs_queue on public.pwa_account_jobs(state,created_at);
create table if not exists public.pwa_password_links (
 token_hash text primary key, job_id uuid not null unique references public.pwa_account_jobs(id),
 courier_id integer not null, email text not null, username text not null, base_password_hash text,
 expires_at timestamptz not null, used_at timestamptz
);
alter table public.pwa_account_jobs enable row level security;
alter table public.pwa_password_links enable row level security;
revoke all on public.pwa_account_jobs,public.pwa_password_links from public,anon,authenticated;
grant select,insert,update on public.pwa_account_jobs,public.pwa_password_links to service_role;

create or replace function public.pwa_auth_enqueue(p_kind text,p_request_id bigint,p_actor text default 'automatic')
returns jsonb language plpgsql security invoker set search_path=public as $$
declare r record; j public.pwa_account_jobs;
begin
 if p_kind='reset' then select * into r from public.pwa_password_reset_requests where id=p_request_id for update;
 elsif p_kind='registration' then select * into r from public.pwa_registration_requests where id=p_request_id for update;
 else raise exception 'Invalid kind'; end if;
 if not found or r.status<>'new' then raise exception 'Request is not pending'; end if;
 insert into public.pwa_account_jobs(kind,request_id,courier_id,email,username,actor)
 values(p_kind,p_request_id,r.courier_id,lower(trim(r.email)),trim(r.courier_name),p_actor)
 on conflict(kind,request_id) do nothing;
 select * into j from public.pwa_account_jobs where kind=p_kind and request_id=p_request_id;
 -- A manual correction of trusted master data can be checked again. Never retry a possibly sent email.
 if p_actor<>'automatic' and j.state in ('manual','failed') then
  update public.pwa_account_jobs set state='queued',actor=p_actor,courier_id=r.courier_id,email=lower(trim(r.email)),username=trim(r.courier_name),note='',updated_at=now() where id=j.id returning * into j;
 end if;
 return jsonb_build_object('id',j.id,'state',j.state);
end $$;

create or replace function public.pwa_auth_claim()
returns setof public.pwa_account_jobs language plpgsql security invoker set search_path=public as $$
begin
 update public.pwa_account_jobs set state=case when state='sending' then 'uncertain' else 'failed' end,
 note='A háttérfolyamat megszakadt; adminellenőrzés szükséges.',updated_at=now()
 where state in ('processing','sending') and updated_at<now()-interval '5 minutes';
 return query update public.pwa_account_jobs set state='processing',updated_at=now()
 where id=(select id from public.pwa_account_jobs where state='queued' order by created_at for update skip locked limit 1) returning *;
end $$;

create or replace function public.pwa_auth_prepare(p_job uuid,p_hash text)
returns jsonb language plpgsql security invoker set search_path=public as $$
declare j public.pwa_account_jobs; m public.courier_master; u public.pwa_users; r record; reason text;
begin
 select * into j from public.pwa_account_jobs where id=p_job for update;
 if not found or j.state<>'processing' then raise exception 'Invalid job state'; end if;
 perform pg_advisory_xact_lock(701801,j.courier_id);
 select * into m from public.courier_master where courier_id=j.courier_id;
 select * into u from public.pwa_users where courier_id=j.courier_id;
 if j.kind='reset' then select * into r from public.pwa_password_reset_requests where id=j.request_id;
 else select * into r from public.pwa_registration_requests where id=j.request_id; end if;
 if r.status is distinct from 'new' or r.courier_id is distinct from j.courier_id or lower(trim(r.email)) is distinct from j.email
 then reason='A kérelem közben megváltozott.';
 elsif m.courier_id is null or m.active is not true then reason='Nincs aktív futártörzsadat.';
 elsif j.email='' or lower(trim(coalesce(nullif(m.email,''),m.billing_email,'')))<>j.email then reason='A törzsben rögzített e-mail nem egyezik.';
 elsif u.id is not null and (u.active is not true or coalesce(u.role,'') not in ('user','courier')) then reason='A meglévő fiók nem módosítható automatikusan.';
 elsif u.id is not null and lower(trim(coalesce(u.email,'')))<>j.email then reason='A mobilfiók e-mail-címe eltér a törzstől.';
 elsif j.kind='reset' and (u.id is null or lower(trim(coalesce(u.email,'')))<>j.email) then reason='Nincs egyező aktív mobilfiók.';
 elsif j.kind='registration' and lower(trim(coalesce(m.courier_name,'')))<>lower(trim(j.username)) then reason='A törzsben rögzített név nem egyezik.';
 elsif exists(select 1 from public.pwa_users where lower(trim(username))=lower(trim(m.courier_name)) and courier_id<>j.courier_id) then reason='A név másik fiókhoz tartozik.';
 elsif exists(select 1 from public.pwa_account_jobs where courier_id=j.courier_id and id<>j.id and state in ('sending','sent','uncertain') and updated_at>now()-interval '30 minutes') then reason='Ehhez a futárhoz már történt levélküldés az elmúlt 30 percben.';
 end if;
 if reason is not null then
  update public.pwa_account_jobs set state='manual',note=reason,updated_at=now() where id=j.id;
  if j.kind='reset' then update public.pwa_password_reset_requests set admin_note=reason,updated_at=now() where id=j.request_id;
  else update public.pwa_registration_requests set admin_note=reason,updated_at=now() where id=j.request_id; end if;
  return jsonb_build_object('ready',false,'state','manual');
 end if;
 if p_hash !~ '^[0-9a-f]{64}$' then raise exception 'Invalid token hash'; end if;
 -- No password or account changes happen before the user redeems the link.
 insert into public.pwa_password_links(token_hash,job_id,courier_id,email,username,base_password_hash,expires_at)
 values(p_hash,j.id,j.courier_id,j.email,coalesce(u.username,m.courier_name),u.password_hash,now()+interval '30 minutes');
 update public.pwa_account_jobs set state='sending',updated_at=now() where id=j.id;
 return jsonb_build_object('ready',true,'email',j.email,'username',coalesce(u.username,m.courier_name));
end $$;

create or replace function public.pwa_auth_finish(p_job uuid,p_sent boolean)
returns void language plpgsql security invoker set search_path=public as $$
declare j public.pwa_account_jobs; msg text;
begin
 select * into j from public.pwa_account_jobs where id=p_job for update;
 if not found or j.state<>'sending' then raise exception 'Invalid job state'; end if;
 msg=case when p_sent then 'Jelszóbeállító link elküldve (30 percig érvényes).' else 'A levélküldés eredménye nem igazolt; automatikusan nem ismételjük.' end;
 update public.pwa_account_jobs set state=case when p_sent then 'sent' else 'uncertain' end,note=msg,updated_at=now() where id=j.id;
 if j.kind='reset' then
  update public.pwa_password_reset_requests set status=case when p_sent then 'sent' else status end,admin_note=msg,
  sent_at=case when p_sent then now() else sent_at end,sent_by=j.actor,updated_at=now() where id=j.request_id and status='new';
 else
  update public.pwa_registration_requests set status=case when p_sent then 'approved' else status end,admin_note=msg,updated_at=now() where id=j.request_id and status='new';
 end if;
end $$;

create or replace function public.pwa_auth_redeem(p_hash text,p_password_hash text)
returns boolean language plpgsql security invoker set search_path=public as $$
declare t public.pwa_password_links; j public.pwa_account_jobs; u public.pwa_users; m public.courier_master; request_status text;
begin
 select * into t from public.pwa_password_links where token_hash=p_hash;
 if not found or t.used_at is not null or t.expires_at<=now() then return false; end if;
 perform pg_advisory_xact_lock(701801,t.courier_id);
 select * into t from public.pwa_password_links where token_hash=p_hash for update;
 if t.used_at is not null or t.expires_at<=now() then return false; end if;
 select * into j from public.pwa_account_jobs where id=t.job_id;
 if j.kind='reset' then select status into request_status from public.pwa_password_reset_requests where id=j.request_id;
 else select status into request_status from public.pwa_registration_requests where id=j.request_id; end if;
 if request_status='rejected' then return false; end if;
 select * into m from public.courier_master where courier_id=t.courier_id;
 if m.active is not true or lower(trim(coalesce(nullif(m.email,''),m.billing_email,'')))<>t.email then return false; end if;
 select * into u from public.pwa_users where courier_id=t.courier_id for update;
 if u.password_hash is distinct from t.base_password_hash then return false; end if;
 if u.id is not null and (u.active is not true or u.role not in ('user','courier') or lower(trim(coalesce(u.email,'')))<>t.email) then return false; end if;
 if p_password_hash not like 'pbkdf2_sha256$260000$%' then raise exception 'Invalid password hash'; end if;
 insert into public.pwa_users(courier_id,username,email,role,active,password_hash,password_updated_at,updated_at)
 values(t.courier_id,t.username,t.email,'user',true,p_password_hash,now(),now())
 on conflict(courier_id) do update set password_hash=excluded.password_hash,password_updated_at=now(),updated_at=now();
 update public.pwa_password_links set used_at=now() where token_hash=p_hash;
 -- Other outstanding links for the same account are invalidated too.
 update public.pwa_password_links set used_at=now() where courier_id=t.courier_id and used_at is null;
 return true;
end $$;

create or replace function public.pwa_auth_request_trigger() returns trigger
language plpgsql security invoker set search_path=public as $$
begin
 if new.status='new' then perform public.pwa_auth_enqueue(case when TG_TABLE_NAME='pwa_password_reset_requests' then 'reset' else 'registration' end,new.id); end if;
 return new;
end $$;
drop trigger if exists pwa_auth_reset_queue on public.pwa_password_reset_requests;
create trigger pwa_auth_reset_queue after insert on public.pwa_password_reset_requests for each row execute function public.pwa_auth_request_trigger();
drop trigger if exists pwa_auth_registration_queue on public.pwa_registration_requests;
create trigger pwa_auth_registration_queue after insert or update of email,courier_name,status on public.pwa_registration_requests for each row execute function public.pwa_auth_request_trigger();
revoke all on function public.pwa_auth_enqueue(text,bigint,text),public.pwa_auth_claim(),public.pwa_auth_prepare(uuid,text),public.pwa_auth_finish(uuid,boolean),public.pwa_auth_redeem(text,text),public.pwa_auth_request_trigger() from public,anon,authenticated;
grant execute on function public.pwa_auth_enqueue(text,bigint,text),public.pwa_auth_claim(),public.pwa_auth_prepare(uuid,text),public.pwa_auth_finish(uuid,boolean),public.pwa_auth_redeem(text,text),public.pwa_auth_request_trigger() to service_role;
notify pgrst,'reload schema';
commit;
