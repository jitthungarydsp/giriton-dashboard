begin;

insert into storage.buckets (id, name, public)
values ('hub-session-cache', 'hub-session-cache', false)
on conflict (id) do update set public = false;

drop policy if exists hub_session_cache_service_only on storage.objects;
create policy hub_session_cache_service_only
on storage.objects as restrictive
for all to anon, authenticated
using (bucket_id <> 'hub-session-cache')
with check (bucket_id <> 'hub-session-cache');

commit;
