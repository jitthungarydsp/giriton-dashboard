begin;

create table if not exists public.pwa_quality_outreach_cases (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    work_date date not null,
    topic text not null check (topic in ('lateShift','uncleanedTimeWindowLate','noShow')),
    reference text not null,
    item_count integer not null check (item_count > 0),
    active boolean not null default true,
    tracked boolean not null default false,
    unique (courier_id, work_date, topic, reference)
);

create table if not exists public.pwa_quality_outreach_emails (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    send_day date not null,
    case_ids uuid[] not null check (cardinality(case_ids) > 0),
    state text not null default 'sending' check (state in ('sending','sent','uncertain')),
    claimed_at timestamptz not null default now(),
    sent_at timestamptz,
    provider_id text,
    check (state <> 'sent' or sent_at is not null),
    unique (courier_id, send_day)
);

create index if not exists pwa_quality_outreach_month on public.pwa_quality_outreach_cases(work_date) where active;
create index if not exists pwa_quality_outreach_sent_cases on public.pwa_quality_outreach_emails using gin(case_ids) where state = 'sent';
alter table public.pwa_quality_outreach_cases enable row level security;
alter table public.pwa_quality_outreach_emails enable row level security;
revoke all on public.pwa_quality_outreach_cases, public.pwa_quality_outreach_emails from public, anon, authenticated;
grant select, insert, update on public.pwa_quality_outreach_cases, public.pwa_quality_outreach_emails to service_role;

create or replace function public.pwa_refresh_quality_outreach(p_month date, p_through date)
returns void language plpgsql security invoker set search_path = '' as $$
begin
    if p_month <> date_trunc('month', p_month)::date or p_through < p_month
       or p_through >= p_month + interval '1 month'
       or p_through > (now() at time zone 'Europe/Budapest')::date then
        raise exception 'Invalid quality outreach window';
    end if;
    perform pg_advisory_xact_lock(947261, (p_month - date '2000-01-01'));
    update public.pwa_quality_outreach_cases set active=false
      where work_date between p_month and p_through and active;
    insert into public.pwa_quality_outreach_cases(courier_id,work_date,topic,reference,item_count)
    select courier_id,work_date,topic,reference,max(item_count)
    from (
        select r.courier_id::text, left(coalesce(s->>'date',s->>'shiftDate'),10)::date as work_date,
               case when e.value in ('late','késett','kesett') then 'lateShift' else 'noShow' end as topic,
               coalesce(nullif(concat_ws('-', nullif(substring(t.start_at from '[0-9]{2}:[0-9]{2}'), ''),
                                              nullif(substring(t.end_at from '[0-9]{2}:[0-9]{2}'), '')), ''), 'Műszak') as reference,
               1 as item_count
        from public.courier_shift_overview_raw r
        cross join lateral jsonb_array_elements(
            case when jsonb_typeof(r.response_json->'shifts')='array' then r.response_json->'shifts' else '[]'::jsonb end
        ) s
        cross join lateral (select lower(trim(coalesce(nullif(s->>'evaluation',''),s->>'status',''))) as value) e
        cross join lateral (select coalesce(nullif(s->>'plannedStart',''),s->>'plannedStartAt') as start_at,
                                   coalesce(nullif(s->>'plannedEnd',''),s->>'plannedEndAt') as end_at) t
        where r.year=extract(year from p_month) and r.month=extract(month from p_month)
          and r.dsp_id=8 and r.status_code=200
          and left(coalesce(s->>'date',s->>'shiftDate'),10) between p_month::text and p_through::text
          and e.value in ('late','késett','kesett','no_show','no show','did_not_come','did not come','nem jelent meg')
        union all
        -- Quality outreach only uses a delay explicitly reported by Courier Hub.
        -- Do not infer a case from stop deltaMinutes, and do not substitute billed counts.
        select r.courier_id::text,
               left(coalesce(route->>'deliveryDate',route->>'delivery_date'),10)::date,
               'uncleanedTimeWindowLate',
               btrim(coalesce(route->>'routeId',route->>'route_id',route->>'id')),
               greatest(case
                   when coalesce(route->>'dataportDelayedOrderCount','') ~ '^[0-9]+$'
                       then (route->>'dataportDelayedOrderCount')::integer
                   else 0
               end,0)
        from (
            select courier_id,dsp_id,year,month,status_code,response_json
            from public.courier_financial_overview_raw_bud1
            where route_layer='COMBINED'
            union all
            select courier_id,dsp_id,year,month,status_code,response_json
            from public.courier_financial_overview_raw_bud2
            where route_layer='COMBINED'
        ) r
        cross join lateral jsonb_array_elements(
            case when jsonb_typeof(r.response_json->'routes')='array'
                 then r.response_json->'routes' else '[]'::jsonb end
        ) route
        where r.year=extract(year from p_month) and r.month=extract(month from p_month)
          and r.dsp_id=8 and r.status_code=200
          and left(coalesce(route->>'deliveryDate',route->>'delivery_date'),10)
              between p_month::text and p_through::text
          and btrim(coalesce(route->>'routeId',route->>'route_id',route->>'id','')) <> ''
          and btrim(coalesce(route->>'routeId',route->>'route_id',route->>'id','')) !~ '[,;[:space:]]'
          and case
              when coalesce(route->>'dataportDelayedOrderCount','') ~ '^[0-9]+$'
                  then (route->>'dataportDelayedOrderCount')::integer
              else 0
          end > 0
    ) source
    group by courier_id,work_date,topic,reference
    on conflict(courier_id,work_date,topic,reference)
    do update set item_count=excluded.item_count, active=true;
    update public.pwa_quality_outreach_cases o set tracked=true
      from public.pwa_quality_outreach_overview v
      where v.id=o.id and not o.tracked and o.work_date between p_month and p_through
        and v.state in ('not_complained','complained');
end;
$$;

create or replace view public.pwa_quality_outreach_overview
with (security_invoker=true) as
select o.id,o.courier_id,o.work_date,o.topic,o.reference,o.item_count,o.tracked,
       coalesce(nullif(m.courier_name,''),nullif(h.name,''),o.courier_id) as courier_name,
       c.id as complaint_id,
       case when c.is_forwarded or d.state='sent' then 'forwarded'
            when c.status='closed' then 'closed'
            when c.is_pending or d.state='prepared' then 'in_progress'
            when c.id is not null then 'complained' else 'not_complained' end as state,
       e.sent_at as last_email_sent_at,
       'hub_validated'::text as source
from public.pwa_quality_outreach_cases o
left join public.courier_master m on m.courier_id::text=o.courier_id
left join lateral (
    select min(nullif(i.name_without_identifier,'')) as name from public.courier_hub_courier_identity_raw i
    where i.courier_id::text=o.courier_id and i.dsp_id=8
) h on true
left join lateral (
    select c.id,c.status,
           (c.status='forwarded' or c.forwarded_at is not null or f.state='sent') as is_forwarded,
           coalesce(f.state in ('queued','processing','prepared','uncertain'),false) as is_pending
    from public.pwa_quality_complaints c
    left join public.pwa_quality_complaint_deliveries f on f.complaint_id=c.id
    where c.courier_id=o.courier_id and c.work_month=date_trunc('month',o.work_date)::date
      and (
        (o.topic='uncleanedTimeWindowLate' and c.topic in ('uncleanedTimeWindowLate','cleanedTimeWindowLate') and
          (c.affected_items @> jsonb_build_array(jsonb_build_object('routeId',o.reference))
           or f.payload->>'route_id'=o.reference))
        or (o.topic in ('lateShift','noShow') and c.topic=o.topic
            and c.affected_items @> jsonb_build_array(jsonb_build_object('date',o.work_date::text)))
      )
    order by (c.status='forwarded' or c.forwarded_at is not null or coalesce(f.state='sent',false)) desc,
             coalesce(f.state in ('queued','processing','prepared','uncertain'),false) desc,
             (c.status='closed') desc,c.created_at desc,c.id
    limit 1
) c on true
left join settlement.route_delay_form_draft d on o.topic='uncleanedTimeWindowLate' and
    d.courier_id=o.courier_id and d.work_date=o.work_date and d.route_id=o.reference
left join lateral (
    select max(sent_at) as sent_at from public.pwa_quality_outreach_emails e
    where e.state='sent' and e.case_ids @> array[o.id]
) e on true
where o.active;

create or replace function public.pwa_create_outreach_complaint(p_id uuid, p_actor text)
returns uuid language plpgsql security invoker set search_path = '' as $$
declare
    selected public.pwa_quality_outreach_overview;
    created uuid;
begin
    -- Serialize with normal complaint inserts while the saved case is checked.
    lock table public.pwa_quality_complaints in share row exclusive mode;
    select * into selected from public.pwa_quality_outreach_overview where id=p_id and tracked;
    if not found or selected.state in ('forwarded','closed','in_progress') then return null; end if;
    if selected.complaint_id is not null then return selected.complaint_id; end if;
    insert into public.pwa_quality_complaints(request_id,courier_id,courier_name,topic,work_month,message,status,affected_items,created_by)
    values (p_id,selected.courier_id,selected.courier_name,selected.topic,date_trunc('month',selected.work_date)::date,
        case selected.topic when 'lateShift' then 'Műszakkésés ellenőrzése.'
          when 'noShow' then 'No-show jelzés ellenőrzése.' else 'Nem mentesített címkésés ellenőrzése.' end,
        'open',jsonb_build_array(jsonb_build_object('date',selected.work_date::text,'label',selected.reference,
            'routeId',case when selected.topic='uncleanedTimeWindowLate' then selected.reference else '' end,
            'category',case when selected.topic='uncleanedTimeWindowLate' then 'Túra alatti késés' else 'Műszak' end)),p_actor)
    on conflict(request_id) do nothing returning id into created;
    return created;
end;
$$;

create or replace function public.pwa_claim_quality_outreach_email(p_courier text, p_cases uuid[])
returns setof public.pwa_quality_outreach_emails
language sql security invoker set search_path = '' as $$
    insert into public.pwa_quality_outreach_emails(courier_id,send_day,case_ids)
    select p_courier,(now() at time zone 'Europe/Budapest')::date,array_agg(v.id order by v.id)
    from public.pwa_quality_outreach_overview v
    where v.courier_id=p_courier and v.id=any(p_cases) and v.tracked and v.state='not_complained'
    having count(*)>0
    on conflict(courier_id,send_day) do nothing
    returning *;
$$;

create or replace function public.pwa_import_quality_outreach_receipts(p_rows jsonb)
returns integer language plpgsql security invoker set search_path = '' as $$
declare
    receipt record;
    matched uuid[];
    expected integer;
    imported integer := 0;
begin
    for receipt in select * from jsonb_to_recordset(p_rows)
        as r(courier_id text, sent_at timestamptz, provider_id text, items jsonb)
    loop
        expected := jsonb_array_length(receipt.items);
        select array_agg(o.id order by o.id) into matched
          from jsonb_to_recordset(receipt.items) as i(work_date date,topic text,reference text)
          join public.pwa_quality_outreach_cases o on o.courier_id=receipt.courier_id
             and o.work_date=i.work_date and o.topic=i.topic and o.reference=i.reference;
        if coalesce(cardinality(matched),0) <> expected or expected=0 or receipt.sent_at > now()
           or coalesce(receipt.provider_id,'')='' then
            raise exception 'Outreach receipt contains an unmatched case or invalid timestamp';
        end if;
        insert into public.pwa_quality_outreach_emails(courier_id,send_day,case_ids,state,sent_at,provider_id)
        values (receipt.courier_id,(receipt.sent_at at time zone 'Europe/Budapest')::date,matched,'sent',receipt.sent_at,receipt.provider_id)
        on conflict (courier_id,send_day) do nothing;
        if not found and not exists (
            select 1 from public.pwa_quality_outreach_emails e
             where e.courier_id=receipt.courier_id and e.send_day=(receipt.sent_at at time zone 'Europe/Budapest')::date
               and e.provider_id=receipt.provider_id and e.case_ids=matched and e.state='sent'
        ) then raise exception 'A different email already occupies the courier send date'; end if;
        update public.pwa_quality_outreach_cases set tracked=true where id=any(matched);
        imported := imported+1;
    end loop;
    return imported;
end;
$$;

revoke all on public.pwa_quality_outreach_overview from public, anon, authenticated;
grant select on public.pwa_quality_outreach_overview to service_role;
revoke all on function public.pwa_refresh_quality_outreach(date,date), public.pwa_create_outreach_complaint(uuid,text), public.pwa_claim_quality_outreach_email(text,uuid[]), public.pwa_import_quality_outreach_receipts(jsonb) from public, anon, authenticated;
grant execute on function public.pwa_refresh_quality_outreach(date,date), public.pwa_create_outreach_complaint(uuid,text), public.pwa_claim_quality_outreach_email(text,uuid[]), public.pwa_import_quality_outreach_receipts(jsonb) to service_role;
notify pgrst, 'reload schema';
commit;
