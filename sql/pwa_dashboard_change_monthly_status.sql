-- Explicit admin action only; installation does not change any existing state.
begin;
create schema if not exists pwa_dashboard_read;
create table if not exists pwa_dashboard_read.monthly_status_change_audit (
    id uuid primary key default gen_random_uuid(), courier_id text not null,
    period_start date not null, target text not null, note text not null,
    changed_by text not null, previous_states jsonb not null, created_at timestamptz not null default now()
);
revoke all on pwa_dashboard_read.monthly_status_change_audit from public, anon, authenticated;
grant usage on schema pwa_dashboard_read to service_role;
grant select, insert on pwa_dashboard_read.monthly_status_change_audit to service_role;

create or replace function settlement.pwa_change_monthly_status(
    p_courier_id text, p_period_start date, p_target text, p_note text, p_actor text
) returns jsonb language plpgsql security invoker set search_path = pg_catalog
as $$
declare
    v_actions text[] := array['settlement','tig','invoice_submit','invoice_check','invoice_payment'];
    v_targets text[] := array['settlement_wait','tig_wait','tig_accept','invoice_upload','invoice_check','payment_wait'];
    v_index integer;
    v_step integer;
    v_completed integer;
    v_name text;
    v_has_tig boolean;
    v_states jsonb;
begin
    if nullif(trim(p_note), '') is null or nullif(trim(p_actor), '') is null
       or nullif(trim(p_courier_id), '') is null
       or p_period_start <> date_trunc('month', p_period_start)::date then
        raise exception 'A futár, hónap és módosítási megjegyzés kötelező.';
    end if;
    v_index := array_position(v_targets, p_target);
    if v_index is null then raise exception 'Ismeretlen célstátusz.'; end if;
    perform pg_advisory_xact_lock(hashtextextended('pwa_monthly_payment:' || p_courier_id || ':' || p_period_start, 0));
    if exists (select 1 from settlement.courier_monthly_closure where courier_id = p_courier_id
        and period_start = p_period_start and status = 'done')
       or exists (select 1 from public.peopleforce_card_statuses where courier_id::text = p_courier_id
        and document_month = p_period_start and action_key = 'invoice_payment' and status = 'done') then
        raise exception 'A kifizetés már lezárva. Előbb a Kifizetés fülön nyisd vissza.';
    end if;
    if exists (select 1 from public.peopleforce_complaints where courier_id::text = p_courier_id
        and document_month = p_period_start and document_type in ('settlement','tig','invoice_submit','invoice_check')
        and status not in ('resolved','closed','deleted') and nullif(trim(admin_response), '') is null and responded_at is null) then
        raise exception 'Előbb válaszold meg vagy zárd le a nyitott reklamációt.';
    end if;
    select courier_name into v_name from settlement.courier_finance_snapshot where courier_id = p_courier_id
        and period_start = p_period_start order by version desc limit 1;
    if not found then raise exception 'Nincs mentett havi elszámolás.'; end if;
    if exists (select 1 from public.peopleforce_card_statuses where courier_id::text = p_courier_id
        and document_month = p_period_start and action_key = 'manual_invoice_skip' and status = 'done') then
        raise exception 'Kézi számlázási kihagyás aktív. A Dokumentumok / Kifizetés nézetben kezeld a folyamatot.';
    end if;
    if v_index >= 2 and exists (select 1 from settlement.mobile_settlement_period_config
        where period_start = p_period_start and visibility_mode = 'settlement_only') then
        raise exception 'A TIG a hónap beállítása szerint rejtve van.';
    end if;
    select exists (select 1 from public.peopleforce_documents where courier_id::text = p_courier_id
        and document_month = p_period_start and document_type = 'tig'
        and coalesce(note,'') not ilike '%Folyamat azonosító:%') into v_has_tig;
    if p_target = 'tig_wait' and v_has_tig then
        raise exception 'Már van TIG dokumentum. Válaszd a TIG elfogadásra vár státuszt.';
    end if;
    if v_index >= 3 and not v_has_tig then raise exception 'Előbb készítsd el a TIG dokumentumot.'; end if;
    if v_index >= 5 and not exists (select 1 from public.peopleforce_documents where courier_id::text = p_courier_id
        and document_month = p_period_start and document_type = 'invoice'
        and coalesce(note,'') not ilike '%Folyamat azonosító:%') then
        raise exception 'Előbb fel kell tölteni a havi számlát.';
    end if;
    select coalesce(jsonb_agg(to_jsonb(s)), '[]'::jsonb) into v_states from public.peopleforce_card_statuses s
        where courier_id::text = p_courier_id and document_month = p_period_start
        and action_key = any(v_actions);
    insert into pwa_dashboard_read.monthly_status_change_audit
        (courier_id,period_start,target,note,changed_by,previous_states)
        values (p_courier_id,p_period_start,p_target,p_note,p_actor,v_states);
    delete from public.peopleforce_card_statuses where courier_id::text = p_courier_id
        and document_month = p_period_start and action_key = any(v_actions);
    v_completed := case p_target when 'settlement_wait' then 0 when 'tig_wait' then 1
        when 'tig_accept' then 1 when 'invoice_upload' then 2 when 'invoice_check' then 3 else 4 end;
    for v_step in 1..5 loop
        if v_step <= v_completed or (v_step = v_completed + 1 and p_target <> 'tig_wait') then
            insert into public.peopleforce_card_statuses
                (courier_id,courier_name,document_month,action_key,status,status_note,updated_by,updated_at)
                values (p_courier_id,v_name,p_period_start,v_actions[v_step],
                    case when v_step <= v_completed then 'done' else 'open' end,
                    'Admin státuszváltás: ' || p_target || '. ' || p_note,p_actor,now());
        end if;
    end loop;
    return jsonb_build_object('ok',true,'target',p_target);
end;
$$;
revoke all on function settlement.pwa_change_monthly_status(text,date,text,text,text) from public, anon, authenticated;
grant execute on function settlement.pwa_change_monthly_status(text,date,text,text,text) to service_role;
notify pgrst, 'reload schema';
commit;
