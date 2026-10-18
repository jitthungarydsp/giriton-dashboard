-- Requires pwa_dashboard_change_monthly_status.sql. Installation changes no
-- courier records. An explicit admin request executes both changes atomically.
begin;

create table if not exists pwa_dashboard_read.invoice_complaint_closure_audit (
    id uuid primary key default gen_random_uuid(),
    courier_id text not null,
    period_start date not null,
    note text not null,
    changed_by text not null,
    previous_complaints jsonb not null,
    created_at timestamptz not null default now()
);
revoke all on pwa_dashboard_read.invoice_complaint_closure_audit from public, anon, authenticated;
grant select, insert on pwa_dashboard_read.invoice_complaint_closure_audit to service_role;

create or replace function settlement.pwa_change_monthly_status_with_complaints(
    p_courier_id text, p_period_start date, p_target text, p_note text, p_actor text
) returns jsonb language plpgsql security invoker set search_path = pg_catalog
as $$
declare
    v_previous jsonb;
    v_result jsonb;
    v_closed integer;
begin
    if p_target is distinct from 'payment_wait' then
        raise exception 'Reklamáció lezárása csak Kifizetésre vár célstátusszal kérhető.';
    end if;
    if nullif(trim(p_note), '') is null or nullif(trim(p_actor), '') is null
       or nullif(trim(p_courier_id), '') is null or p_period_start is null
       or p_period_start <> date_trunc('month', p_period_start)::date then
        raise exception 'A futár, hónap és módosítási megjegyzés kötelező.';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('pwa_monthly_payment:' || p_courier_id || ':' || p_period_start, 0));
    select coalesce(jsonb_agg(to_jsonb(c)), '[]'::jsonb) into v_previous
    from (
        select * from public.peopleforce_complaints
        where courier_id::text = p_courier_id and document_month = p_period_start
          and document_type = 'invoice_check'
          and coalesce(status, 'new') not in ('resolved', 'closed', 'deleted')
        for update
    ) c;

    update public.peopleforce_complaints
    set status = 'closed',
        admin_response = concat_ws(E'\n\n', nullif(trim(admin_response), ''),
            'Admin jóváhagyás, kifizetésre engedve: ' || p_note),
        responded_by = p_actor, responded_at = now()
    where id::text in (select item->>'id' from jsonb_array_elements(v_previous) item);
    get diagnostics v_closed = row_count;

    -- All original safeguards still apply, including other unanswered
    -- complaints, uploaded invoice/TIG and already closed payments. Any
    -- exception rolls back the complaint closure as well as the status change.
    v_result := settlement.pwa_change_monthly_status(
        p_courier_id, p_period_start, p_target, p_note, p_actor
    );
    if v_closed > 0 then
        insert into pwa_dashboard_read.invoice_complaint_closure_audit
            (courier_id, period_start, note, changed_by, previous_complaints)
        values (p_courier_id, p_period_start, p_note, p_actor, v_previous);
    end if;
    return v_result || jsonb_build_object('closedInvoiceComplaints', v_closed);
end;
$$;

revoke all on function settlement.pwa_change_monthly_status_with_complaints(text,date,text,text,text)
    from public, anon, authenticated;
grant execute on function settlement.pwa_change_monthly_status_with_complaints(text,date,text,text,text)
    to service_role;
notify pgrst, 'reload schema';
commit;
