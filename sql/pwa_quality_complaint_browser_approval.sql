begin;

create or replace function public.pwa_prepare_quality_form(p_id uuid, p_actor text, p_payload jsonb)
returns setof public.pwa_quality_complaint_deliveries
language plpgsql security invoker set search_path = public
as $$
declare
    delivery public.pwa_quality_complaint_deliveries;
begin
    perform 1 from public.pwa_quality_complaints where id = p_id and status = 'open' for update;
    if not found then return; end if;

    select * into delivery from public.pwa_quality_complaint_deliveries where complaint_id = p_id for update;
    if found and delivery.state = 'prepared' then
        return next delivery;
        return;
    end if;
    if delivery.state in ('processing', 'uncertain', 'sent') then return; end if;
    if p_payload->>'complaint_id' is distinct from p_id::text then return; end if;

    return query insert into public.pwa_quality_complaint_deliveries (complaint_id, payload, state, approved_by)
        values (p_id, p_payload, 'prepared', p_actor)
        on conflict (complaint_id) do update set
            payload = excluded.payload, state = 'prepared', approved_by = p_actor,
            approved_at = now(), updated_at = now(), lease_token = null, lease_until = null,
            submit_started_at = null, last_error = '', confirmation = ''
        returning *;
end;
$$;

revoke all on function public.pwa_prepare_quality_form(uuid, text, jsonb) from public, anon, authenticated;
grant execute on function public.pwa_prepare_quality_form(uuid, text, jsonb) to service_role;
notify pgrst, 'reload schema';

commit;
