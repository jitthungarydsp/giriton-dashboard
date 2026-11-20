-- Run after daily_limit.sql and browser_approval.sql, BEFORE deploying the Route ID UI/API.
-- Existing complaints, deliveries and financial records are preserved.
begin;
lock table public.pwa_quality_complaints in share row exclusive mode;
lock table public.pwa_quality_complaint_deliveries in share row exclusive mode;

create table if not exists public.pwa_quality_complaint_route_claims (
    route_id text primary key check (route_id <> '' and route_id = btrim(route_id)),
    complaint_id uuid not null references public.pwa_quality_complaints(id),
    courier_id text not null
);
alter table public.pwa_quality_complaint_route_claims enable row level security;
revoke all on public.pwa_quality_complaint_route_claims from public, anon, authenticated, service_role;

-- Prefer an already submitted/in-flight case over an older unsubmitted duplicate.
-- Include both original and actual form routes, so a historical mismatch cannot
-- permit another submission of an already used route. Do not guess missing IDs.
insert into public.pwa_quality_complaint_route_claims (route_id, complaint_id, courier_id)
select distinct on (r.route_id) r.route_id, c.id, c.courier_id
from public.pwa_quality_complaints c
left join public.pwa_quality_complaint_deliveries d on d.complaint_id = c.id
cross join lateral (
    select btrim(item->>'routeId') as route_id from jsonb_array_elements(c.affected_items) item
    union
    select btrim(d.payload->>'route_id') where d.state in ('sent','processing','uncertain','prepared','queued')
) r
where c.topic in ('cleanedTimeWindowLate','uncleanedTimeWindowLate')
  and coalesce(r.route_id, '') <> '' and r.route_id !~ '[,;[:space:]]'
order by r.route_id, case when d.state = 'sent' or c.status = 'forwarded' then 0
    when d.state in ('processing','uncertain','prepared','queued') then 1 else 2 end,
    c.created_at, c.id
on conflict do nothing;

create or replace function public.pwa_find_quality_route_complaint(p_route_id text, p_courier_id text)
returns setof public.pwa_quality_complaints
language sql stable security definer set search_path = '' as $$
    select c.* from public.pwa_quality_complaint_route_claims r
    join public.pwa_quality_complaints c on c.id = r.complaint_id
    where r.route_id = btrim(p_route_id) and c.courier_id = p_courier_id;
$$;
revoke all on function public.pwa_find_quality_route_complaint(text,text) from public, anon, authenticated;
grant execute on function public.pwa_find_quality_route_complaint(text,text) to service_role;

create or replace function public.pwa_claim_quality_complaint_days()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
    route_ids text[];
    claimed_route text;
    day_claim record;
begin
    if new.topic in ('cleanedTimeWindowLate','uncleanedTimeWindowLate') then
        select array_agg(distinct btrim(item->>'routeId')) into route_ids
        from jsonb_array_elements(new.affected_items) item;
        if cardinality(route_ids) <> 1 or route_ids[1] is null or route_ids[1] = ''
           or route_ids[1] ~ '[,;[:space:]]'
           or exists (select 1 from jsonb_array_elements(new.affected_items) item
                      where coalesce(btrim(item->>'routeId'), '') = '') then
            raise exception 'Egy reklamációhoz pontosan egy Route ID szükséges.' using errcode = '22023';
        end if;
        claimed_route := route_ids[1];
        insert into public.pwa_quality_complaint_route_claims (route_id, complaint_id, courier_id)
            values (claimed_route, new.id, new.courier_id) on conflict do nothing;
        if not found then
            raise exception 'Ehhez a Route ID-hoz már van reklamáció: %.', claimed_route using errcode = 'PZ001';
        end if;
    elsif new.topic = 'noShow' then
        -- No-show has no tour: retain the existing per-courier/day protection.
        for day_claim in select distinct item->>'date' as work_date
            from jsonb_array_elements(new.affected_items) item order by work_date
        loop
            insert into public.pwa_quality_complaint_day_claims (courier_id, work_date, bucket, complaint_id)
                values (new.courier_id, day_claim.work_date::date, 'no_show', new.id) on conflict do nothing;
            if not found then
                raise exception 'Erre a napra már van no-show reklamáció.' using errcode = 'PZ001';
            end if;
        end loop;
    end if;
    return new;
end;
$$;
revoke all on function public.pwa_claim_quality_complaint_days() from public, anon, authenticated, service_role;

-- Check approval and worker transitions too, including legacy duplicate cases.
create or replace function public.pwa_guard_quality_delivery_route()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
    c public.pwa_quality_complaints;
    route_ids text[];
    owner_id uuid;
begin
    select * into c from public.pwa_quality_complaints where id = new.complaint_id;
    if c.topic not in ('cleanedTimeWindowLate','uncleanedTimeWindowLate') then return new; end if;
    select array_agg(distinct btrim(item->>'routeId')) into route_ids
        from jsonb_array_elements(c.affected_items) item;
    if cardinality(route_ids) <> 1 or route_ids[1] is null or route_ids[1] = ''
       or route_ids[1] ~ '[,;[:space:]]'
       or exists (select 1 from jsonb_array_elements(c.affected_items) item
                  where coalesce(btrim(item->>'routeId'), '') = '')
       or new.payload->>'route_id' is distinct from route_ids[1] then
        raise exception 'A beküldéshez a reklamáció pontosan egy, mentett Route ID-ja szükséges.' using errcode = '22023';
    end if;
    insert into public.pwa_quality_complaint_route_claims (route_id, complaint_id, courier_id)
        values (route_ids[1], c.id, c.courier_id) on conflict do nothing;
    select complaint_id into owner_id from public.pwa_quality_complaint_route_claims where route_id = route_ids[1];
    if owner_id is distinct from c.id then
        raise exception 'Ehhez a Route ID-hoz már másik reklamáció tartozik: %.', route_ids[1] using errcode = 'PZ001';
    end if;
    return new;
end;
$$;
revoke all on function public.pwa_guard_quality_delivery_route() from public, anon, authenticated, service_role;
drop trigger if exists pwa_guard_quality_delivery_route on public.pwa_quality_complaint_deliveries;
create trigger pwa_guard_quality_delivery_route before insert or update
    on public.pwa_quality_complaint_deliveries for each row
    execute function public.pwa_guard_quality_delivery_route();

-- Protect identity after creation; status, replies and audit history remain editable.
create or replace function public.pwa_guard_quality_complaint_route_identity()
returns trigger language plpgsql set search_path = '' as $$
begin
    if new.courier_id is distinct from old.courier_id or new.topic is distinct from old.topic
       or new.affected_items is distinct from old.affected_items then
        raise exception 'A reklamáció futára, típusa és mentett tételei nem írhatók át.' using errcode = '22023';
    end if;
    return new;
end;
$$;
revoke all on function public.pwa_guard_quality_complaint_route_identity() from public, anon, authenticated, service_role;
drop trigger if exists pwa_guard_quality_complaint_route_identity on public.pwa_quality_complaints;
create trigger pwa_guard_quality_complaint_route_identity before update
    on public.pwa_quality_complaints for each row
    execute function public.pwa_guard_quality_complaint_route_identity();
notify pgrst, 'reload schema';
commit;
