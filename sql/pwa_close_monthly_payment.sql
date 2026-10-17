-- Install an explicit admin closure action. Installation changes no financial rows.
-- The function runs only when the admin presses the monthly closure button.
begin;
create or replace function settlement.pwa_close_monthly_payment(
    p_courier_id text, p_period_start date, p_snapshot_id uuid,
    p_invoice_number text, p_note text, p_actor text
)
returns jsonb
language plpgsql security invoker
set search_path = pg_catalog
as $$
declare
    v_snapshot settlement.courier_finance_snapshot%rowtype;
    v_closure settlement.courier_monthly_closure%rowtype;
    v_reserve settlement.courier_target_reserve_monthly%rowtype;
    v_profile public.courier_master%rowtype;
    v_values jsonb;
    v_amount numeric;
    v_advance numeric;
    v_end date := (p_period_start + interval '1 month - 1 day')::date;
    v_plan uuid;
    v_now timestamptz := now();
begin
    if p_period_start <> date_trunc('month', p_period_start)::date
       or nullif(trim(p_courier_id), '') is null
       or nullif(trim(p_actor), '') is null then
        raise exception 'Hiányzó vagy hibás havi kifizetési adatok.';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('pwa_monthly_payment:' || p_courier_id || ':' || p_period_start, 0));
    select * into v_closure from settlement.courier_monthly_closure
        where courier_id = p_courier_id and period_start = p_period_start and period_end = v_end for update;
    if v_closure.status = 'done' then
        return jsonb_build_object('ok', true, 'alreadyClosed', true, 'payableHuf', v_closure.payable_huf);
    end if;
    select * into v_snapshot from settlement.courier_finance_snapshot
        where courier_id = p_courier_id and period_start = p_period_start
        order by version desc, created_at desc limit 1 for update;
    if not found or v_snapshot.id is distinct from p_snapshot_id then
        raise exception 'A mentett elszámolás megváltozott. Frissítsd a Kifizetés fület.';
    end if;
    select jsonb_object_agg(item_key, amount_value) into v_values
        from settlement.courier_finance_snapshot_item where snapshot_id = v_snapshot.id and section = 'finance';
    v_values := coalesce(v_values, '{}'::jsonb);
    if not (v_values ? 'payable') then
        raise exception 'Hiányzik a mentett kifizetendő összeg.';
    end if;
    v_amount := round((v_values->>'payable')::numeric);
    if nullif(trim(p_note), '') is null or position(
        regexp_replace(abs(v_amount)::text, '[^0-9]', '', 'g') in
        regexp_replace(p_note, '[^0-9]', '', 'g')) = 0 then
        raise exception 'A lezárási megjegyzés kötelező, és tartalmaznia kell az összeget.';
    end if;
    if not exists (select 1 from public.peopleforce_card_statuses
        where courier_id::text = p_courier_id and document_month = p_period_start
        and action_key in ('invoice_check', 'manual_invoice_skip') and status = 'done') then
        raise exception 'A számla még nincs jóváhagyva.';
    end if;
    select * into v_profile from public.courier_master where courier_id::text = p_courier_id limit 1;
    if not found or nullif(trim(v_profile.bank_account_number), '') is null then
        raise exception 'Hiányzik a kedvezményezett bankszámlaszáma.';
    end if;
    select coalesce(sum(amount_huf), 0) into v_advance from settlement.courier_salary_advance_installment
        where courier_id = p_courier_id and period_start <= v_end and period_end >= p_period_start
        and status in ('open', 'done');
    if v_advance <> abs(coalesce((v_values->>'salary_advance')::numeric, 0)) then
        raise exception 'A fizetéselőleg eltér a mentett elszámolástól. Előbb frissítsd az elszámolást.';
    end if;
    select * into v_reserve from settlement.courier_target_reserve_monthly
        where courier_id = p_courier_id and period_start = p_period_start and period_end = v_end for update;
    if found then
        if v_reserve.reserve_addition_huf <> abs(coalesce((v_values->>'reserve')::numeric, 0))
           or v_reserve.insurance_fee_huf <> abs(coalesce((v_values->>'insurance_fee')::numeric, 0)) then
            raise exception 'A céltartalék vagy biztosítás eltér a mentett elszámolástól.';
        end if;
        if v_reserve.status <> 'done' then
            update settlement.courier_target_reserve_monthly set status = 'done', closed_at = v_now,
                closed_by = p_actor, updated_at = v_now where id = v_reserve.id;
            update public.courier_target_reserve set
                "CT_Z_FT" = round(v_reserve.reserve_after_huf)::text,
                "CT_NY_FT" = round(v_reserve.reserve_addition_huf)::text,
                current_reserve_huf = round(v_reserve.reserve_after_huf),
                reserve_deduction_huf = round(v_reserve.reserve_addition_huf),
                insurance_active = v_reserve.insurance_active_after,
                reserve_status = 'done', updated_at = v_now
                where "courier_ID"::text = p_courier_id;
        end if;
    elsif abs(coalesce((v_values->>'reserve')::numeric, 0)) + abs(coalesce((v_values->>'insurance_fee')::numeric, 0)) > 0 then
        raise exception 'Hiányzik a mentett havi céltartalék. Előbb frissítsd az elszámolást.';
    end if;
    for v_plan in select distinct plan_id from settlement.courier_salary_advance_installment
        where courier_id = p_courier_id and period_start <= v_end and period_end >= p_period_start and status = 'open'
    loop
        update settlement.courier_salary_advance_installment set status = 'done', closed_at = v_now,
            closed_by = p_actor, updated_at = v_now where plan_id = v_plan and courier_id = p_courier_id
            and period_start <= v_end and period_end >= p_period_start and status = 'open';
        if not exists (select 1 from settlement.courier_salary_advance_installment where plan_id = v_plan and status = 'open') then
            update settlement.courier_salary_advance_plan set status = 'done', closed_at = v_now,
                closed_by = p_actor, updated_at = v_now where id = v_plan;
        end if;
    end loop;
    insert into settlement.courier_monthly_closure (courier_id, courier_name, session_id, period_start, period_end,
        bank_account_number, recipient_name, payment_note, invoice_number, payable_huf, status, snapshot, closed_at, closed_by, updated_at)
    values (p_courier_id, v_snapshot.courier_name, nullif(v_snapshot.session_id, '')::uuid, p_period_start, v_end,
        v_profile.bank_account_number, coalesce(nullif(v_profile.company_name, ''), v_snapshot.courier_name),
        concat_ws('-', p_courier_id, nullif(trim(p_invoice_number), '')), trim(p_invoice_number), v_amount, 'done',
        jsonb_build_object('finance_snapshot_id', v_snapshot.id, 'finance_snapshot_version', v_snapshot.version,
            'payable_huf', v_amount, 'close_note', p_note, 'finance_items', v_values,
            'base_huf', coalesce((v_values->>'base')::numeric, 0),
            'tip_huf', coalesce((v_values->>'tip')::numeric, 0),
            'salary_advance_huf', abs(coalesce((v_values->>'salary_advance')::numeric, 0)),
            'reserve_addition_huf', abs(coalesce((v_values->>'reserve')::numeric, 0)),
            'insurance_fee_huf', abs(coalesce((v_values->>'insurance_fee')::numeric, 0))), v_now, p_actor, v_now)
    on conflict (courier_id, period_start, period_end) do update set
        bank_account_number = excluded.bank_account_number, recipient_name = excluded.recipient_name,
        payment_note = excluded.payment_note, invoice_number = excluded.invoice_number, payable_huf = excluded.payable_huf,
        status = 'done', snapshot = excluded.snapshot, closed_at = v_now, closed_by = p_actor, updated_at = v_now;
    insert into public.peopleforce_card_statuses (courier_id, courier_name, action_key, document_month, status, status_note, updated_by, updated_at)
    values (p_courier_id, v_snapshot.courier_name, 'invoice_payment', p_period_start, 'done', p_note, p_actor, v_now)
    on conflict (courier_id, action_key, document_month) do update set
        status = 'done', status_note = excluded.status_note, updated_by = p_actor, updated_at = v_now;
    return jsonb_build_object('ok', true, 'alreadyClosed', false, 'payableHuf', v_amount);
end;
$$;
revoke all on function settlement.pwa_close_monthly_payment(text,date,uuid,text,text,text) from public, anon, authenticated;
grant execute on function settlement.pwa_close_monthly_payment(text,date,uuid,text,text,text) to service_role;
notify pgrst, 'reload schema';
create or replace function settlement.pwa_reopen_monthly_payment(
    p_courier_id text, p_period_start date, p_note text, p_actor text
)
returns jsonb language plpgsql security invoker set search_path = pg_catalog
as $$
declare
    v_reserve settlement.courier_target_reserve_monthly%rowtype;
    v_end date := (p_period_start + interval '1 month - 1 day')::date;
    v_now timestamptz := now();
begin
    if nullif(trim(p_courier_id), '') is null or nullif(trim(p_note), '') is null
       or nullif(trim(p_actor), '') is null or p_period_start <> date_trunc('month', p_period_start)::date then
        raise exception 'Hiányzó visszanyitási adatok.';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('pwa_monthly_payment:' || p_courier_id || ':' || p_period_start, 0));
    if exists (select 1 from settlement.courier_target_reserve_monthly
               where courier_id = p_courier_id and period_start > p_period_start and status = 'done') then
        raise exception 'Későbbi hónap már lezárva. A korábbi céltartalék nem állítható vissza automatikusan.';
    end if;
    update settlement.courier_monthly_closure set status = 'reopened', reopened_at = v_now,
        reopened_by = p_actor, updated_at = v_now
        where courier_id = p_courier_id and period_start = p_period_start and period_end = v_end and status = 'done';
    select * into v_reserve from settlement.courier_target_reserve_monthly
        where courier_id = p_courier_id and period_start = p_period_start and period_end = v_end for update;
    if found and v_reserve.status = 'done' then
        update settlement.courier_target_reserve_monthly set status = 'in_progress', closed_at = null,
            closed_by = null, updated_at = v_now where id = v_reserve.id;
        update public.courier_target_reserve set "CT_Z_FT" = round(v_reserve.reserve_before_huf)::text,
            "CT_NY_FT" = round(v_reserve.reserve_addition_huf)::text,
            current_reserve_huf = round(v_reserve.reserve_before_huf),
            reserve_deduction_huf = round(v_reserve.reserve_addition_huf),
            insurance_active = v_reserve.insurance_active_before, reserve_status = 'in_progress', updated_at = v_now
            where "courier_ID"::text = p_courier_id;
    end if;
    update settlement.courier_salary_advance_plan set status = 'open', closed_at = null,
        closed_by = null, updated_at = v_now where id in (
            select plan_id from settlement.courier_salary_advance_installment where courier_id = p_courier_id
            and period_start = p_period_start and period_end = v_end and status = 'done');
    update settlement.courier_salary_advance_installment set status = 'open', closed_at = null,
        closed_by = null, updated_at = v_now where courier_id = p_courier_id
        and period_start = p_period_start and period_end = v_end and status = 'done';
    insert into public.peopleforce_card_statuses (courier_id,courier_name,action_key,document_month,status,status_note,updated_by,updated_at)
    values (p_courier_id, coalesce((select courier_name from public.courier_master where courier_id::text = p_courier_id limit 1), p_courier_id),
        'invoice_payment', p_period_start, 'open', 'Havi kifizetés elutasítva / visszanyitva. ' || p_note, p_actor, v_now)
    on conflict (courier_id,action_key,document_month) do update set status = 'open',
        status_note = excluded.status_note, updated_by = p_actor, updated_at = v_now;
    return jsonb_build_object('ok', true);
end;
$$;
revoke all on function settlement.pwa_reopen_monthly_payment(text,date,text,text) from public, anon, authenticated;
grant execute on function settlement.pwa_reopen_monthly_payment(text,date,text,text) to service_role;
notify pgrst, 'reload schema';
commit;
