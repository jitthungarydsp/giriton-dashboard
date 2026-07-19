-- Racz Csaba cleanup minden nem-master tablaban.
--
-- Cel:
--   Racz Csaba ujraimportalasahoz toroljuk az osszes regi/hibas sort
--   minden tablából, KIVEVE a futar master/torsz tablakat.
--
-- Kihagyott tablák:
--   public.courier_master
--   public.core_couriers
--
-- Azonositas:
--   courier_id / driver_id / user_number = 2875
--   email = csaba.racz66@gmail.com
--   nev tartalmazza egyszerre: Racz/Rácz + Csaba
--   JSON/text mezokben: 2875 vagy csaba.racz66@gmail.com vagy Racz/Rácz + Csaba
--
-- Hasznalat:
--   1. Supabase SQL Editorban eloszor futtasd a DRY RUN blokkot.
--   2. Ha a lista jo, futtasd az APPLY DELETE blokkot.


-- ---------------------------------------------------------------------------
-- 1) DRY RUN - csak listaz, NEM torol
-- ---------------------------------------------------------------------------
do $$
declare
    t record;
    c record;
    where_parts text[];
    where_sql text;
    count_sql text;
    found_count bigint;
begin
    create temp table if not exists tmp_racz_cleanup_preview (
        table_name text,
        matched_rows bigint
    ) on commit drop;

    truncate tmp_racz_cleanup_preview;

    for t in
        select table_schema, table_name
        from information_schema.tables
        where table_schema = 'public'
          and table_type = 'BASE TABLE'
          and table_name not in ('courier_master', 'core_couriers')
        order by table_name
    loop
        where_parts := array[]::text[];

        for c in
            select column_name, data_type, udt_name
            from information_schema.columns
            where table_schema = t.table_schema
              and table_name = t.table_name
        loop
            if c.column_name in (
                'courier_id',
                'driver_id',
                'courierId',
                'driverId',
                'user_number',
                'user_id'
            ) then
                where_parts := array_append(
                    where_parts,
                    format('%I::text = %L', c.column_name, '2875')
                );
            end if;

            if c.column_name in (
                'email',
                'billing_email',
                'contact_email',
                'courier_email',
                'driver_email'
            ) then
                where_parts := array_append(
                    where_parts,
                    format('lower(%I::text) = %L', c.column_name, 'csaba.racz66@gmail.com')
                );
            end if;

            if c.column_name in (
                'courier_name',
                'driver_name',
                'name',
                'full_name',
                'employee_name',
                'user_name'
            ) then
                where_parts := array_append(
                    where_parts,
                    format(
                        '(lower(%I::text) like %L and lower(%I::text) like %L)',
                        c.column_name,
                        '%csaba%',
                        c.column_name,
                        '%r%cz%'
                    )
                );
            end if;

            if c.column_name in ('response_json', 'raw_payload', 'payload', 'data')
               or c.udt_name in ('json', 'jsonb') then
                where_parts := array_append(
                    where_parts,
                    format(
                        '(%I::text like %L or lower(%I::text) like %L or (lower(%I::text) like %L and lower(%I::text) like %L))',
                        c.column_name,
                        '%2875%',
                        c.column_name,
                        '%csaba.racz66@gmail.com%',
                        c.column_name,
                        '%csaba%',
                        c.column_name,
                        '%r%cz%'
                    )
                );
            end if;
        end loop;

        if coalesce(array_length(where_parts, 1), 0) = 0 then
            continue;
        end if;

        where_sql := array_to_string(where_parts, ' or ');
        count_sql := format(
            'select count(*) from %I.%I where %s',
            t.table_schema,
            t.table_name,
            where_sql
        );

        execute count_sql into found_count;

        if found_count > 0 then
            insert into tmp_racz_cleanup_preview(table_name, matched_rows)
            values (t.table_name, found_count);
        end if;
    end loop;
end $$;

select *
from tmp_racz_cleanup_preview
order by table_name;


-- ---------------------------------------------------------------------------
-- 2) APPLY DELETE - csak akkor futtasd, ha a fenti DRY RUN lista jo
-- ---------------------------------------------------------------------------
-- do $$
-- declare
--     t record;
--     c record;
--     where_parts text[];
--     where_sql text;
--     delete_sql text;
--     deleted_count bigint;
-- begin
--     create temp table if not exists tmp_racz_cleanup_deleted (
--         table_name text,
--         deleted_rows bigint
--     ) on commit drop;
--
--     truncate tmp_racz_cleanup_deleted;
--
--     for t in
--         select table_schema, table_name
--         from information_schema.tables
--         where table_schema = 'public'
--           and table_type = 'BASE TABLE'
--           and table_name not in ('courier_master', 'core_couriers')
--         order by table_name
--     loop
--         where_parts := array[]::text[];
--
--         for c in
--             select column_name, data_type, udt_name
--             from information_schema.columns
--             where table_schema = t.table_schema
--               and table_name = t.table_name
--         loop
--             if c.column_name in (
--                 'courier_id',
--                 'driver_id',
--                 'courierId',
--                 'driverId',
--                 'user_number',
--                 'user_id'
--             ) then
--                 where_parts := array_append(
--                     where_parts,
--                     format('%I::text = %L', c.column_name, '2875')
--                 );
--             end if;
--
--             if c.column_name in (
--                 'email',
--                 'billing_email',
--                 'contact_email',
--                 'courier_email',
--                 'driver_email'
--             ) then
--                 where_parts := array_append(
--                     where_parts,
--                     format('lower(%I::text) = %L', c.column_name, 'csaba.racz66@gmail.com')
--                 );
--             end if;
--
--             if c.column_name in (
--                 'courier_name',
--                 'driver_name',
--                 'name',
--                 'full_name',
--                 'employee_name',
--                 'user_name'
--             ) then
--                 where_parts := array_append(
--                     where_parts,
--                     format(
--                         '(lower(%I::text) like %L and lower(%I::text) like %L)',
--                         c.column_name,
--                         '%csaba%',
--                         c.column_name,
--                         '%r%cz%'
--                     )
--                 );
--             end if;
--
--             if c.column_name in ('response_json', 'raw_payload', 'payload', 'data')
--                or c.udt_name in ('json', 'jsonb') then
--                 where_parts := array_append(
--                     where_parts,
--                     format(
--                         '(%I::text like %L or lower(%I::text) like %L or (lower(%I::text) like %L and lower(%I::text) like %L))',
--                         c.column_name,
--                         '%2875%',
--                         c.column_name,
--                         '%csaba.racz66@gmail.com%',
--                         c.column_name,
--                         '%csaba%',
--                         c.column_name,
--                         '%r%cz%'
--                     )
--                 );
--             end if;
--         end loop;
--
--         if coalesce(array_length(where_parts, 1), 0) = 0 then
--             continue;
--         end if;
--
--         where_sql := array_to_string(where_parts, ' or ');
--         delete_sql := format(
--             'delete from %I.%I where %s',
--             t.table_schema,
--             t.table_name,
--             where_sql
--         );
--
--         execute delete_sql;
--         get diagnostics deleted_count = row_count;
--
--         if deleted_count > 0 then
--             insert into tmp_racz_cleanup_deleted(table_name, deleted_rows)
--             values (t.table_name, deleted_count);
--         end if;
--     end loop;
-- end $$;
--
-- select *
-- from tmp_racz_cleanup_deleted
-- order by table_name;
