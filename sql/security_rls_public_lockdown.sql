begin;

-- Supabase security hardening for exposed public schema objects.
-- Run this once in the Supabase SQL Editor for project kifli-dashboard.
-- The dashboard/PWA backend in this repo uses SUPABASE_SERVICE_ROLE_KEY, so
-- service_role keeps access while anon/authenticated direct REST access is closed.

do $$
declare
    obj record;
begin
    for obj in
        select
            n.nspname as schema_name,
            c.relname as object_name
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relkind in ('r', 'p')
          and c.relname not in ('schema_migrations', 'spatial_ref_sys')
        order by c.relname
    loop
        execute format('alter table %I.%I enable row level security', obj.schema_name, obj.object_name);
        execute format('revoke all on table %I.%I from anon', obj.schema_name, obj.object_name);
        execute format('revoke all on table %I.%I from authenticated', obj.schema_name, obj.object_name);
        execute format('grant select, insert, update, delete on table %I.%I to service_role', obj.schema_name, obj.object_name);
    end loop;
end $$;

do $$
declare
    obj record;
begin
    for obj in
        select
            n.nspname as schema_name,
            c.relname as object_name
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relkind in ('v', 'm')
        order by c.relname
    loop
        execute format('revoke all on table %I.%I from anon', obj.schema_name, obj.object_name);
        execute format('revoke all on table %I.%I from authenticated', obj.schema_name, obj.object_name);
        execute format('grant select on table %I.%I to service_role', obj.schema_name, obj.object_name);
    end loop;
end $$;

do $$
declare
    obj record;
begin
    for obj in
        select
            sequence_schema as schema_name,
            sequence_name as object_name
        from information_schema.sequences
        where sequence_schema = 'public'
        order by sequence_name
    loop
        execute format('revoke all on sequence %I.%I from anon', obj.schema_name, obj.object_name);
        execute format('revoke all on sequence %I.%I from authenticated', obj.schema_name, obj.object_name);
        execute format('grant usage, select, update on sequence %I.%I to service_role', obj.schema_name, obj.object_name);
    end loop;
end $$;

-- Audit after running: this should return zero rows for user tables.
select
    n.nspname as schema_name,
    c.relname as table_name,
    c.relrowsecurity as rls_enabled,
    has_table_privilege('anon', format('%I.%I', n.nspname, c.relname), 'select,insert,update,delete') as anon_has_data_privilege,
    has_table_privilege('authenticated', format('%I.%I', n.nspname, c.relname), 'select,insert,update,delete') as authenticated_has_data_privilege
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind in ('r', 'p')
  and c.relname not in ('schema_migrations', 'spatial_ref_sys')
  and (
      not c.relrowsecurity
      or has_table_privilege('anon', format('%I.%I', n.nspname, c.relname), 'select,insert,update,delete')
      or has_table_privilege('authenticated', format('%I.%I', n.nspname, c.relname), 'select,insert,update,delete')
  )
order by c.relname;

notify pgrst, 'reload schema';

commit;
