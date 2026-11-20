-- Legacy migration. Apply pwa_quality_complaint_route_limit.sql AFTER this file.
begin;

create table if not exists public.pwa_quality_complaint_day_claims (
    courier_id text not null,
    work_date date not null,
    bucket text not null check (bucket in ('address_delay', 'no_show')),
    complaint_id uuid not null references public.pwa_quality_complaints(id),
    primary key (courier_id, work_date, bucket)
);

alter table public.pwa_quality_complaint_day_claims enable row level security;
revoke all on public.pwa_quality_complaint_day_claims from public, anon, authenticated, service_role;

create or replace function public.pwa_quality_complaint_day_bucket(topic text, item jsonb)
returns text language sql immutable set search_path = '' as $$
    select case
        when topic = 'noShow' then 'no_show'
        when topic in ('cleanedTimeWindowLate', 'uncleanedTimeWindowLate')
            and not (coalesce(item->>'signalKind', '') = 'route' and coalesce(item->>'category', '') = 'Futárbüntetés')
            then 'address_delay'
    end;
$$;

-- Keep historical duplicates intact while claiming their dates against new submissions.
lock table public.pwa_quality_complaints in share row exclusive mode;
insert into public.pwa_quality_complaint_day_claims (courier_id, work_date, bucket, complaint_id)
select distinct on (c.courier_id, days.work_date, days.bucket) c.courier_id, days.work_date::date, days.bucket, c.id
from public.pwa_quality_complaints c
cross join lateral (
    select item->>'date' as work_date, public.pwa_quality_complaint_day_bucket(c.topic, item) as bucket
    from jsonb_array_elements(c.affected_items) item
) days
where days.bucket is not null and days.work_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
order by c.courier_id, days.work_date, days.bucket, c.created_at, c.id
on conflict do nothing;

create or replace function public.pwa_claim_quality_complaint_days()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
    day_claim record;
begin
    for day_claim in
        select distinct item->>'date' as work_date, public.pwa_quality_complaint_day_bucket(new.topic, item) as bucket
        from jsonb_array_elements(new.affected_items) item
        where public.pwa_quality_complaint_day_bucket(new.topic, item) is not null
        order by work_date, bucket
    loop
        if day_claim.work_date is null or day_claim.work_date !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
            raise exception 'Hiányzó vagy hibás reklamációs dátum.' using errcode = '22023';
        end if;
        insert into public.pwa_quality_complaint_day_claims (courier_id, work_date, bucket, complaint_id)
            values (new.courier_id, day_claim.work_date::date, day_claim.bucket, new.id)
            on conflict do nothing;
        if not found then
            raise exception 'Már van ilyen típusú reklamáció erre a napra.' using errcode = 'PZ001';
        end if;
    end loop;
    return new;
end;
$$;

revoke all on function public.pwa_quality_complaint_day_bucket(text, jsonb), public.pwa_claim_quality_complaint_days()
    from public, anon, authenticated, service_role;
drop trigger if exists pwa_claim_quality_complaint_days on public.pwa_quality_complaints;
create trigger pwa_claim_quality_complaint_days after insert on public.pwa_quality_complaints
    for each row execute function public.pwa_claim_quality_complaint_days();

commit;
