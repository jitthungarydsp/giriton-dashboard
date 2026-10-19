-- Installation changes no courier data. Runtime is restricted to #12345 / 2026-09.
begin;
create or replace function settlement.pwa_commit_worksheet_pilot(
    p_courier_id text, p_period_start date, p_base_snapshot_id uuid,
    p_fingerprint text, p_actor text, p_prepared jsonb
) returns jsonb language plpgsql security invoker set search_path = pg_catalog
as $$
declare
    v_latest settlement.courier_finance_snapshot%rowtype;
    v_id uuid;
    v_total numeric;
    v_income numeric;
    v_deductions numeric;
    v_correction numeric;
    v_tig numeric;
begin
    if p_courier_id is distinct from '12345' or p_period_start is distinct from date '2026-09-01' then
        raise exception 'A munkalap tesztje csak #12345 / 2026-09 hónapra engedélyezett.';
    end if;
    if nullif(trim(p_actor), '') is null or nullif(p_fingerprint, '') is null
       or p_prepared->'metadata'->>'source' is distinct from 'pwa_worksheet_pilot'
       or nullif(trim(p_prepared->'metadata'->>'worksheet_note'), '') is null then
        raise exception 'Hiányzó mentési adatok.';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('pwa_monthly_payment:' || p_courier_id || ':' || p_period_start, 0));
    select * into v_latest from settlement.courier_finance_snapshot
    where courier_id = p_courier_id and period_start = p_period_start
    order by version desc limit 1 for update;
    if not found then raise exception 'Nincs mentett elszámolás.'; end if;
    if exists (select 1 from settlement.courier_monthly_closure where courier_id = p_courier_id
               and period_start = p_period_start and status = 'done')
       or exists (select 1 from public.peopleforce_card_statuses where courier_id::text = p_courier_id
                  and document_month = p_period_start and action_key = 'invoice_payment' and status = 'done') then
        raise exception 'A kifizetés lezárt. A munkalap nem módosítható.';
    end if;
    if v_latest.previous_snapshot_id = p_base_snapshot_id and v_latest.fingerprint = p_fingerprint then
        return jsonb_build_object('ok', true, 'snapshotId', v_latest.id, 'version', v_latest.version, 'unchanged', true);
    end if;
    if v_latest.id is distinct from p_base_snapshot_id then
        raise exception 'Az elszámolás verziója megváltozott. Töltsd újra a munkalapot.';
    end if;
    if jsonb_typeof(p_prepared->'items') is distinct from 'array'
       or jsonb_typeof(p_prepared->'sources') is distinct from 'array' then
        raise exception 'Hiányos pénzügyi munkalap.';
    end if;
    select (p_prepared->'metadata'->>'payable_total')::numeric,
           (p_prepared->'metadata'->>'income_total')::numeric,
           (p_prepared->'metadata'->>'deduction_total')::numeric,
           (p_prepared->'metadata'->>'correction_total')::numeric,
           (p_prepared->'metadata'->>'tig_final_total')::numeric
    into v_total, v_income, v_deductions, v_correction, v_tig;
    if v_total is null or v_income is null or v_deductions is null or v_correction is null or v_tig is null
       or v_total < 0 or v_total <> v_income + v_deductions + v_correction
       or (select count(*) from jsonb_array_elements(p_prepared->'items') i
           where i->>'section' = 'finance' and i->>'item_key' = 'payable'
             and (i->>'amount_value')::numeric = v_total) <> 1
       or (select count(*) from jsonb_array_elements(p_prepared->'items') i
           where i->>'section' = 'tig' and i->>'item_key' = 'tig_final_total'
             and (i->>'amount_value')::numeric = v_tig) <> 1
       or (select coalesce(sum((i->>'amount_value')::numeric),0) from jsonb_array_elements(p_prepared->'items') i
           where i->>'section' = 'tig' and i->>'item_key' not in ('tig_final_total','tig_cash_service')) <> v_tig then
        raise exception 'A pénzügyi és TIG összesítések nem egyeznek.';
    end if;
    insert into settlement.courier_finance_snapshot
        (courier_id,courier_name,period_start,version,source,calculation_mode,warehouse_label,session_id,
         fingerprint,previous_snapshot_id,previous_fingerprint,changed_from_previous,metadata,created_by)
    values (p_courier_id,v_latest.courier_name,p_period_start,v_latest.version+1,'pwa_worksheet_pilot',
            v_latest.calculation_mode,v_latest.warehouse_label,v_latest.session_id,p_fingerprint,
            v_latest.id,v_latest.fingerprint,true,p_prepared->'metadata',p_actor) returning id into v_id;
    insert into settlement.courier_finance_snapshot_item
        (snapshot_id,section,item_key,item_label,amount_value,amount_kind,note,display_order)
    select v_id, x.section,x.item_key,x.item_label,x.amount_value,x.amount_kind,x.note,x.display_order
    from jsonb_to_recordset(p_prepared->'items') as x(section text,item_key text,item_label text,
         amount_value numeric,amount_kind text,note text,display_order integer);
    insert into settlement.courier_finance_snapshot_source (snapshot_id,source_key,source_table,payload,row_count)
    select v_id,x.source_key,x.source_table,x.payload,x.row_count
    from jsonb_to_recordset(p_prepared->'sources') as x(source_key text,source_table text,payload jsonb,row_count integer);
    return jsonb_build_object('ok',true,'snapshotId',v_id,'version',v_latest.version+1);
end;
$$;
revoke all on function settlement.pwa_commit_worksheet_pilot(text,date,uuid,text,text,jsonb) from public,anon,authenticated;
grant execute on function settlement.pwa_commit_worksheet_pilot(text,date,uuid,text,text,jsonb) to service_role;
notify pgrst, 'reload schema';
commit;
