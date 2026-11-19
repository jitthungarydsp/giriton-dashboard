begin;

create table if not exists settlement.google_adjustment_review (
    courier_id text not null,
    period_start date not null,
    reason text not null,
    previous_payable_huf numeric,
    proposed_payable_huf numeric,
    google_delta_huf numeric,
    detected_at timestamptz not null default now(),
    primary key (courier_id, period_start)
);
alter table settlement.google_adjustment_review enable row level security;
revoke all on settlement.google_adjustment_review from public, anon, authenticated;
grant select, insert, update, delete on settlement.google_adjustment_review to service_role;

create or replace function settlement.publish_google_adjustment_snapshot(
    p_courier_id text, p_period_start date, p_base_id uuid,
    p_fingerprint text, p_metadata jsonb, p_items jsonb, p_sources jsonb
) returns text language plpgsql security invoker set search_path = pg_catalog as $$
declare
    v_base settlement.courier_finance_snapshot%rowtype;
    v_id uuid;
    v_reserve jsonb;
    v_reserve_delta numeric := coalesce((p_metadata->>'google_reserve_delta_huf')::numeric, 0);
    v_delta numeric := coalesce((p_metadata->>'google_delta_huf')::numeric, 0);
begin
    perform pg_advisory_xact_lock(hashtextextended('pwa_monthly_payment:' || p_courier_id || ':' || p_period_start, 0));
    select * into v_base from settlement.courier_finance_snapshot
      where courier_id = p_courier_id and period_start = p_period_start and version > 0
      order by version desc limit 1 for update;
    if v_base.id is distinct from p_base_id then
        return 'retry';
    end if;
    -- Refuse a proposal calculated before a concurrent import/edit completed.
    if exists (
        with current_rows as (
            select id::text as id, adjustment_type, amount_huf, valid_from::text as valid_from,
                   valid_to::text as valid_to, coalesce(note, '') as note
            from settlement.courier_settlement_adjustment
            where courier_id = p_courier_id and starts_with(source_key, 'google_bonus_malus:')
              and is_active and deleted_at is null and valid_to >= p_period_start
              and valid_from < p_period_start + interval '1 month'
        ), proposed_rows as (
            select r->>'id' as id, r->>'adjustment_type' as adjustment_type,
                   (r->>'amount_huf')::numeric as amount_huf, r->>'valid_from' as valid_from,
                   r->>'valid_to' as valid_to, coalesce(r->>'note', '') as note
            from jsonb_array_elements(p_sources) s
            cross join lateral jsonb_array_elements(case when s->>'source_key' = 'manual_adjustments'
                                                       then s->'payload' else '[]'::jsonb end) r
            where starts_with(r->>'source_key', 'google_bonus_malus:')
        )
        (select * from current_rows except all select * from proposed_rows)
        union all
        (select * from proposed_rows except all select * from current_rows)
    ) then
        return 'retry';
    end if;
    if exists (select 1 from settlement.courier_monthly_closure where courier_id = p_courier_id
               and period_start = p_period_start and status = 'done')
       or exists (select 1 from public.peopleforce_card_statuses where courier_id::text = p_courier_id
                  and document_month = p_period_start and action_key = 'invoice_payment' and status = 'done') then
        return 'closed';
    end if;
    if exists (select 1 from public.peopleforce_documents where courier_id::text = p_courier_id
               and document_month = p_period_start
               and (document_type in ('invoice', 'cash_invoice', 'kp_invoice')
                    or document_type like 'process:kp_invoice_%:invoice'))
       or exists (select 1 from public.peopleforce_card_statuses where courier_id::text = p_courier_id
                  and document_month = p_period_start and (
                      (action_key in ('invoice_submit','invoice_check','manual_invoice_skip') and status = 'done')
                      or (action_key = 'invoice_payment' and status = 'open'
                          and coalesce(status_note, '') not like 'Új elszámolási verzió miatt%'
                          and coalesce(status_note, '') <> '')
                  )) then
        return 'invoiced';
    end if;
    if v_delta <> v_reserve_delta
       and exists (select 1 from public.peopleforce_documents where courier_id::text = p_courier_id
                   and document_month = p_period_start and document_type = 'tig') then
        return 'issued_tig';
    end if;
    if exists (select 1 from settlement.courier_target_reserve_monthly where courier_id = p_courier_id
               and period_start = p_period_start and status = 'done') then
        return 'closed_reserve';
    end if;
    if v_reserve_delta <> 0 then
        -- A different closing balance changes the opening balance of later months.
        if exists (select 1 from settlement.courier_target_reserve_monthly
                   where courier_id = p_courier_id and period_start > p_period_start)
           or exists (select 1 from settlement.courier_finance_snapshot
                      where courier_id = p_courier_id and period_start > p_period_start and version > 0) then
            return 'reserve_recalculation';
        end if;
        select s->'payload' into v_reserve from jsonb_array_elements(p_sources) s
         where s->>'source_key' = 'target_reserve_month';
        update settlement.courier_target_reserve_monthly
           set payable_before_insurance_huf = (v_reserve->>'payable_before_insurance_huf')::numeric,
               payable_after_insurance_huf = (v_reserve->>'payable_after_insurance_huf')::numeric,
               reserve_addition_huf = (v_reserve->>'reserve_addition_huf')::numeric,
               reserve_after_huf = (v_reserve->>'reserve_after_huf')::numeric,
               calculated_at = now(), updated_at = now()
         where courier_id = p_courier_id and period_start = p_period_start and status = 'in_progress'
           and reserve_before_huf = (v_reserve->>'reserve_before_huf')::numeric
           and reserve_addition_huf + v_reserve_delta = (v_reserve->>'reserve_addition_huf')::numeric
           and reserve_after_huf + v_reserve_delta = (v_reserve->>'reserve_after_huf')::numeric
           and payable_before_insurance_huf + v_delta = (v_reserve->>'payable_before_insurance_huf')::numeric
           and payable_after_insurance_huf + v_delta - v_reserve_delta = (v_reserve->>'payable_after_insurance_huf')::numeric
           and insurance_fee_huf = (v_reserve->>'insurance_fee_huf')::numeric;
        if not found then
            return 'reserve_recalculation';
        end if;
    end if;
    insert into settlement.courier_finance_snapshot
        (courier_id,courier_name,period_start,version,source,calculation_mode,warehouse_label,session_id,
         fingerprint,previous_snapshot_id,previous_fingerprint,changed_from_previous,metadata,created_by)
    values (p_courier_id,v_base.courier_name,p_period_start,v_base.version+1,'devtest_finance',
            v_base.calculation_mode,v_base.warehouse_label,v_base.session_id,p_fingerprint,
            v_base.id,v_base.fingerprint,p_fingerprint is distinct from v_base.fingerprint,
            p_metadata,'google-bonus-malus-sync') returning id into v_id;
    insert into settlement.courier_finance_snapshot_item
        (snapshot_id,section,item_key,item_label,amount_value,amount_kind,note,display_order)
    select v_id,x.section,x.item_key,x.item_label,x.amount_value,x.amount_kind,x.note,x.display_order
      from jsonb_to_recordset(p_items) as x(section text,item_key text,item_label text,
           amount_value numeric,amount_kind text,note text,display_order integer);
    insert into settlement.courier_finance_snapshot_source
        (snapshot_id,source_key,source_table,payload,row_count)
    select v_id,x.source_key,x.source_table,x.payload,x.row_count
      from jsonb_to_recordset(p_sources) as x(source_key text,source_table text,payload jsonb,row_count integer);

    if p_fingerprint is distinct from v_base.fingerprint
       and exists (select 1 from jsonb_array_elements(p_items) i where i->>'section' in ('finance','tig')
                   and i->>'item_key' in ('payable','tig_final_total')
                   and (i->>'amount_value')::numeric is distinct from (
                       select o.amount_value from settlement.courier_finance_snapshot_item o
                        where o.snapshot_id = v_base.id and o.section = i->>'section' and o.item_key = i->>'item_key'
                   ))
       and exists (select 1 from public.peopleforce_card_statuses where courier_id::text = p_courier_id
                    and document_month = p_period_start and action_key in ('settlement','tig') and status = 'done') then
        update public.peopleforce_card_statuses
           set status = 'open', updated_at = now(), updated_by = 'finance-snapshot-refresh',
               status_note = case when action_key = 'settlement'
                 then 'Új pénzügyi snapshot érkezett (' || left(v_id::text, 8) || '); az elszámolást ismét el kell fogadni.'
                 else 'Új elszámolási verzió miatt ismét az elszámolás elfogadására vár.' end
         where courier_id::text = p_courier_id and document_month = p_period_start
           and action_key in ('settlement','tig','invoice_submit','invoice_check','invoice_payment');
    end if;
    delete from settlement.google_adjustment_review where courier_id = p_courier_id and period_start = p_period_start;
    return 'saved';
end;
$$;
revoke all on function settlement.publish_google_adjustment_snapshot(text,date,uuid,text,jsonb,jsonb,jsonb)
    from public, anon, authenticated;
grant execute on function settlement.publish_google_adjustment_snapshot(text,date,uuid,text,jsonb,jsonb,jsonb)
    to service_role;
notify pgrst, 'reload schema';
commit;
