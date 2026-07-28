begin;

do $$
declare
    target_table text;
    id_data_type text;
    id_default text;
begin
    foreach target_table in array array[
        'courier_financial_overview_raw_bud1',
        'courier_financial_overview_raw_bud2',
        'courier_financial_overview_month_raw_bud1',
        'courier_financial_overview_month_raw_bud2'
    ]
    loop
        select data_type, column_default
        into id_data_type, id_default
        from information_schema.columns
        where table_schema = 'public'
          and table_name = target_table
          and column_name = 'id';

        if id_data_type is null or id_default is not null then
            continue;
        end if;

        if id_data_type = 'uuid' then
            execute format(
                'alter table public.%I alter column id set default gen_random_uuid()',
                target_table
            );
        elsif id_data_type in ('integer', 'bigint', 'smallint') then
            execute format(
                'create sequence if not exists public.%I',
                target_table || '_id_seq'
            );
            execute format(
                'select setval(%L::regclass, coalesce((select max(id) from public.%I), 0) + 1, false)',
                'public.' || target_table || '_id_seq',
                target_table
            );
            execute format(
                'alter table public.%I alter column id set default nextval(%L::regclass)',
                target_table,
                'public.' || target_table || '_id_seq'
            );
        end if;
    end loop;
end $$;

commit;
