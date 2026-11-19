begin;

create table if not exists settlement.invoice_notification_delivery (
    id uuid primary key default gen_random_uuid(),
    kind text not null check (kind in ('immediate', 'digest')),
    digest_day date unique,
    events jsonb not null,
    state text not null default 'pending' check (state in ('pending', 'sending', 'sent', 'uncertain')),
    started_at timestamptz,
    finished_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists settlement.invoice_notification_event (
    id bigint generated always as identity primary key,
    kind text not null,
    courier_id text not null,
    courier_name text not null,
    period_start date not null,
    detail text not null,
    requires_immediate boolean not null,
    historical boolean not null,
    digest_day date,
    immediate_delivery uuid references settlement.invoice_notification_delivery(id),
    digest_delivery uuid references settlement.invoice_notification_delivery(id),
    occurred_at timestamptz not null
);

create index if not exists invoice_notification_event_immediate_idx
    on settlement.invoice_notification_event (occurred_at, courier_id, period_start)
    where requires_immediate and immediate_delivery is null;
create index if not exists invoice_notification_event_digest_idx
    on settlement.invoice_notification_event (digest_day, id) where digest_delivery is null;
create index if not exists invoice_notification_delivery_state_idx
    on settlement.invoice_notification_delivery (state, created_at);

alter table settlement.invoice_notification_delivery enable row level security;
alter table settlement.invoice_notification_event enable row level security;
revoke all on settlement.invoice_notification_event, settlement.invoice_notification_delivery
    from public, anon, authenticated;
grant select, update on settlement.invoice_notification_delivery to service_role;

create or replace function settlement.capture_invoice_notification()
returns trigger language plpgsql security definer set search_path = pg_catalog as $$
declare
    v_now timestamptz := statement_timestamp();
    v_local timestamp := v_now at time zone 'Europe/Budapest';
    v_month date := date_trunc('month', v_local)::date;
    v_active date;
    v_kind text;
    v_action text;
    v_detail text;
    v_immediate boolean;
    v_historical boolean;
    v_invoice_event boolean := false;
    v_closed_payment_transition boolean := false;
begin
    if tg_table_name = 'peopleforce_documents' then
        v_kind := 'document:' || new.document_type;
        v_invoice_event := new.document_type in ('invoice', 'cash_invoice', 'kp_invoice')
                           or new.document_type like 'process:kp_invoice_%:invoice';
        v_detail := left(coalesce(nullif(new.title, ''), new.file_name, ''), 250);
    elsif tg_table_name = 'peopleforce_complaints' then
        if tg_op = 'UPDATE' and old.status is not distinct from new.status then
            return new;
        end if;
        v_kind := 'complaint';
        v_detail := new.status;
    else
        if new.action_key not in ('settlement','tig','invoice_submit','invoice_check','invoice_payment')
           and new.action_key !~ '^process:kp_invoice_[^:]+:(settlement|tig|invoice_submit|invoice_check|invoice_payment)$' then
            return new;
        end if;
        v_action := regexp_replace(new.action_key, '^.*:', '');
        if tg_op = 'UPDATE' and old.status is not distinct from new.status then
            return new;
        end if;
        v_kind := 'status:' || v_action;
        v_detail := new.status;
        v_invoice_event := v_action = 'invoice_check' and new.status = 'open'
            and coalesce(new.updated_by, '') <> 'finance-snapshot-refresh';
        if tg_op = 'UPDATE' then
            v_closed_payment_transition := new.action_key = 'invoice_payment' and old.status = 'done';
        end if;
    end if;

    select max(period_start) into v_active from settlement.mobile_settlement_period_config
        where period_start <= v_month
          and (calculation_mode in ('API','Excel') or nullif(btrim(session_id), '') is not null);
    v_active := coalesce(v_active, (v_month - interval '1 month')::date);
    v_historical := new.document_month < v_active and (
        v_closed_payment_transition
        or exists (select 1 from settlement.courier_monthly_closure c where c.courier_id = new.courier_id::text
                   and c.period_start = new.document_month and c.status = 'done')
        or exists (select 1 from public.peopleforce_card_statuses s where s.courier_id::text = new.courier_id::text
                   and s.document_month = new.document_month and s.action_key = 'invoice_payment' and s.status = 'done')
    );
    v_immediate := v_historical or (
        new.document_month = v_active and v_invoice_event and extract(day from v_local) <= 18
    );
    if not v_immediate and not v_invoice_event and v_kind not like 'status:%' and v_kind <> 'complaint' then
        return new;
    end if;

    insert into settlement.invoice_notification_event
        (kind, courier_id, courier_name, period_start, detail, requires_immediate, historical, digest_day, occurred_at)
    values (v_kind, new.courier_id::text, coalesce(nullif(new.courier_name, ''), new.courier_id::text),
            new.document_month, v_detail, v_immediate, v_historical,
            case when v_kind like 'status:%' or v_kind = 'complaint' or (v_invoice_event and not v_immediate)
                 then v_local::date + case when v_local::time >= time '08:00' then 1 else 0 end end, v_now);
    return new;
end;
$$;
revoke all on function settlement.capture_invoice_notification() from public, anon, authenticated;

drop trigger if exists invoice_notification_document on public.peopleforce_documents;
create trigger invoice_notification_document after insert on public.peopleforce_documents
    for each row execute function settlement.capture_invoice_notification();
drop trigger if exists invoice_notification_status on public.peopleforce_card_statuses;
create trigger invoice_notification_status after insert or update of status on public.peopleforce_card_statuses
    for each row execute function settlement.capture_invoice_notification();
drop trigger if exists invoice_notification_complaint on public.peopleforce_complaints;
create trigger invoice_notification_complaint after insert or update of status on public.peopleforce_complaints
    for each row execute function settlement.capture_invoice_notification();

create or replace function settlement.claim_invoice_notification()
returns setof settlement.invoice_notification_delivery
language plpgsql security definer set search_path = pg_catalog as $$
declare
    v_local timestamp := now() at time zone 'Europe/Budapest';
    v_cutoff date := v_local::date - case when v_local::time < time '08:00' then 1 else 0 end;
    v_day date;
    v_courier text;
    v_period date;
    v_ids bigint[];
    v_events jsonb;
    v_delivery uuid;
begin
    perform pg_advisory_xact_lock(hashtextextended('invoice-notification-claim', 0));
    update settlement.invoice_notification_delivery set state = 'uncertain', finished_at = now()
        where state = 'sending' and started_at < now() - interval '15 minutes';

    -- Pick a quiet window so transfer/cash uploads and the ensuing check can share one email.
    select e.courier_id, e.period_start into v_courier, v_period
        from settlement.invoice_notification_event e
        where e.requires_immediate and e.immediate_delivery is null
        group by e.courier_id, e.period_start
        having max(e.occurred_at) <= now() - interval '30 seconds'
        order by min(e.occurred_at) limit 1;
    if found then
        select array_agg(e.id), jsonb_agg(to_jsonb(e) order by e.occurred_at, e.id) into v_ids, v_events
            from settlement.invoice_notification_event e
            where e.courier_id = v_courier and e.period_start = v_period
              and e.requires_immediate and e.immediate_delivery is null
              and e.occurred_at <= now() - interval '30 seconds';
        insert into settlement.invoice_notification_delivery(kind, events)
            values ('immediate', v_events) returning id into v_delivery;
        update settlement.invoice_notification_event set immediate_delivery = v_delivery where id = any(v_ids);
    end if;

    -- Changes from a transaction that committed after the morning email roll forward.
    update settlement.invoice_notification_event e
       set digest_day = v_cutoff + case when exists (
           select 1 from settlement.invoice_notification_delivery d where d.digest_day = v_cutoff
       ) then 1 else 0 end
     where e.digest_delivery is null and e.digest_day <= v_cutoff
       and exists (select 1 from settlement.invoice_notification_delivery d where d.digest_day = e.digest_day);

    -- A missed morning with events is picked up with its original digest date.
    select min(e.digest_day) into v_day from settlement.invoice_notification_event e
        where e.digest_delivery is null and e.digest_day <= v_cutoff
          and not exists (select 1 from settlement.invoice_notification_delivery d where d.digest_day = e.digest_day);
    if v_day is null and v_local::time >= time '08:00' and extract(day from v_local) >= 19
       and not exists (select 1 from settlement.invoice_notification_delivery d where d.digest_day = v_cutoff) then
        v_day := v_cutoff;
    end if;
    if v_day is not null then
        select array_agg(e.id), jsonb_agg(to_jsonb(e) order by e.occurred_at, e.id) into v_ids, v_events
            from settlement.invoice_notification_event e where e.digest_day = v_day and e.digest_delivery is null;
        insert into settlement.invoice_notification_delivery(kind, digest_day, events)
            values ('digest', v_day, coalesce(v_events, '[]'::jsonb)) returning id into v_delivery;
        update settlement.invoice_notification_event set digest_delivery = v_delivery where id = any(v_ids);
    end if;

    return query
    update settlement.invoice_notification_delivery d set state = 'sending', started_at = now()
        where d.id = (select q.id from settlement.invoice_notification_delivery q where q.state = 'pending'
                      order by q.created_at, q.id limit 1)
        returning d.*;
end;
$$;
revoke all on function settlement.claim_invoice_notification() from public, anon, authenticated;
grant execute on function settlement.claim_invoice_notification() to service_role;

notify pgrst, 'reload schema';
commit;
