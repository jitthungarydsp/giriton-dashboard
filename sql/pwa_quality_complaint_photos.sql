-- Run after pwa_quality_complaint_management.sql.
begin;
alter table public.pwa_quality_complaints
    add column if not exists attachments jsonb not null default '[]'::jsonb;

create or replace function public.pwa_attach_quality_complaint_photo(p_id uuid, p_photo jsonb)
returns setof public.pwa_quality_complaints
language plpgsql security invoker set search_path = public as $$
declare v_row public.pwa_quality_complaints;
begin
    select * into v_row from public.pwa_quality_complaints where id = p_id for update;
    if not found then raise exception 'Complaint not found'; end if;
    if exists (select 1 from jsonb_array_elements(v_row.attachments) x
               where x->>'sha256' = p_photo->>'sha256') then
        return next v_row;
        return;
    end if;
    if v_row.status <> 'open' then raise exception 'Only open complaints accept photos'; end if;
    if jsonb_array_length(v_row.attachments) >= 5 then raise exception 'Maximum 5 photos'; end if;
    if coalesce(p_photo->>'sha256', '') !~ '^[0-9a-f]{64}$'
       or coalesce(p_photo->>'mime_type', '') not in ('image/jpeg', 'image/png', 'image/webp')
       or coalesce(p_photo->>'storage_path', '') not like 'quality-complaints/' || p_id::text || '/%'
    then raise exception 'Invalid photo metadata'; end if;
    return query update public.pwa_quality_complaints
        set attachments = attachments || jsonb_build_array(p_photo)
        where id = p_id returning *;
end;
$$;
revoke all on function public.pwa_attach_quality_complaint_photo(uuid,jsonb) from public, anon, authenticated;
grant execute on function public.pwa_attach_quality_complaint_photo(uuid,jsonb) to service_role;
notify pgrst, 'reload schema';
commit;
