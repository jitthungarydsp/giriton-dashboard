-- Run after pwa_quality_complaints.sql. Safe to run again.
begin;
alter table public.pwa_quality_complaints
    drop constraint if exists pwa_quality_complaints_status_check;
alter table public.pwa_quality_complaints
    add column if not exists admin_response text not null default '',
    add column if not exists responded_at timestamptz,
    add column if not exists responded_by text,
    add column if not exists forwarded_at timestamptz,
    add column if not exists forwarding_reference text,
    add column if not exists closed_at timestamptz,
    add column if not exists closed_by text,
    add column if not exists history jsonb not null default '[]'::jsonb;
update public.pwa_quality_complaints set status = case
    when status in ('new', 'in_review') then 'open'
    when status in ('resolved', 'rejected') then 'closed' else status end;
alter table public.pwa_quality_complaints alter column status set default 'open';
alter table public.pwa_quality_complaints add constraint pwa_quality_complaints_status_check
    check (status in ('open', 'forwarded', 'closed'));
create index if not exists pwa_quality_complaints_status_created_idx
    on public.pwa_quality_complaints (status, created_at desc);

create or replace function public.pwa_manage_quality_complaint(
    p_id uuid, p_action text, p_message text, p_actor text, p_reference text default ''
) returns setof public.pwa_quality_complaints
language plpgsql security invoker set search_path = public as $$
declare v_row public.pwa_quality_complaints; v_status text; v_now timestamptz := now();
begin
    select * into v_row from public.pwa_quality_complaints where id = p_id for update;
    if not found then raise exception 'Complaint not found'; end if;
    if v_row.status = 'closed' then raise exception 'Complaint already closed'; end if;
    if p_action not in ('reply', 'forward', 'close') then raise exception 'Invalid action'; end if;
    if p_action in ('reply', 'close') and length(btrim(p_message)) not between 5 and 5000 then
        raise exception 'Response required';
    end if;
    if p_action = 'forward' and (v_row.status <> 'open' or length(btrim(p_reference)) < 3) then
        raise exception 'Forwarding requires an open complaint and delivery reference';
    end if;
    v_status := case p_action when 'forward' then 'forwarded' when 'close' then 'closed' else v_row.status end;
    return query update public.pwa_quality_complaints set
        status = v_status,
        admin_response = case when p_action in ('reply', 'close') then btrim(p_message) else admin_response end,
        responded_at = case when p_action in ('reply', 'close') then v_now else responded_at end,
        responded_by = case when p_action in ('reply', 'close') then p_actor else responded_by end,
        forwarded_at = case when p_action = 'forward' then v_now else forwarded_at end,
        forwarding_reference = case when p_action = 'forward' then btrim(p_reference) else forwarding_reference end,
        closed_at = case when p_action = 'close' then v_now else closed_at end,
        closed_by = case when p_action = 'close' then p_actor else closed_by end,
        history = history || jsonb_build_array(jsonb_build_object(
            'action', p_action, 'status', v_status, 'message', btrim(p_message),
            'actor', p_actor, 'at', v_now, 'reference', btrim(p_reference)))
    where id = p_id returning *;
end;
$$;
revoke all on function public.pwa_manage_quality_complaint(uuid,text,text,text,text) from public, anon, authenticated;
grant execute on function public.pwa_manage_quality_complaint(uuid,text,text,text,text) to service_role;
notify pgrst, 'reload schema';
commit;
