-- Eles tabla-atnevezes prefixelt nevekre.
--
-- Fontos:
-- - Ez nem view-kat keszit, hanem a meglevo VALODI tablakat nevezi at.
-- - Csak akkor futtasd elesben, ha utana a kodban is atvezetjuk az uj neveket.
-- - Ha a korabbi alias view-k mar letrejottek az uj neveken, azokat elobb torli.
-- - Adatot nem torol.

do $$
declare
    item record;
    source_kind text;
    target_kind text;
begin
    for item in
        select *
        from (
            values
                ('courier_master', 'core_couriers', 'CORE: futartorzzs, courier ID alapu alapadatok.'),

                ('dsp_driver_detail_raw', 'raw_dsp_driver_detail', 'RAW: DSP fetch-drivers-detail nyers JSON.'),
                ('dsp_drivers_live_raw', 'raw_dsp_live_drivers', 'RAW: DSP fetch-drivers live snapshot.'),
                ('dsp_attendance_raw', 'raw_dsp_attendance', 'RAW: DSP fetch-attendance napi JSON.'),
                ('dsp_vehicle_assignments', 'raw_dsp_vehicle_assignments', 'RAW: DSP vehicle assignments.'),
                ('giriton_shifts_raw', 'raw_giriton_shifts', 'RAW: Giriton muszak adatok.'),
                ('giriton_attendance_raw', 'raw_giriton_attendance', 'RAW: Giriton be- es kijelentkezes.'),
                ('foglalasok_raw', 'raw_muszakpro_bookings', 'RAW: MuszakPro/Foglalasok adatok.'),
                ('jitt_invoice_performance_bud1_raw', 'raw_jitt_invoice_perf_bud1', 'RAW: Courier Hub performance BUD1.'),
                ('jitt_invoice_performance_bud2_raw', 'raw_jitt_invoice_perf_bud2', 'RAW: Courier Hub performance BUD2.'),
                ('jitt_workbook_imports', 'raw_jitt_workbook_imports', 'RAW: JITT workbook import futasok.'),
                ('jitt_workbook_main_raw', 'raw_jitt_workbook_main', 'RAW: JITT workbook fo tabla.'),
                ('jitt_workbook_detail_raw', 'raw_jitt_workbook_detail', 'RAW: JITT workbook reszletes tabla.'),

                ('dsp_order_arrivals', 'stg_dsp_order_arrivals', 'STAGE: cimszintu erkezes es idoablak bontas.'),
                ('dsp_route_delay_statistics', 'stg_dsp_route_delay', 'STAGE: route keses statisztika.'),
                ('dsp_route_distance_calculated', 'stg_dsp_route_distance', 'STAGE: szamolt route tavolsag.'),
                ('dsp_route_km_latest', 'stg_dsp_route_km_latest', 'STAGE: live km/tura allapot.'),
                ('dsp_attendance_couriers', 'stg_dsp_attendance_couriers', 'STAGE: DSP attendance futar bontas.'),
                ('dsp_attendance_shifts', 'stg_dsp_attendance_shifts', 'STAGE: DSP attendance muszak bontas.'),
                ('dsp_attendance_routes', 'stg_dsp_attendance_routes', 'STAGE: DSP attendance route bontas.'),
                ('dsp_shift_route_summary', 'stg_dsp_shift_route_summary', 'STAGE: muszak-route osszekapcsolas.'),

                ('dsp_driver_month_summary', 'mart_dsp_driver_month', 'MART: havi futar KPI.'),
                ('dsp_company_kpi_summary', 'mart_dsp_company_kpi', 'MART: ceges havi KPI.'),
                ('courier_card_stats', 'mart_courier_card_stats', 'MART: Kiflis kartya gyors statisztika.'),

                ('jitt_invoice_imports', 'bill_jitt_invoice_imports', 'BILLING: invoice import futasok.'),
                ('jitt_invoice_summary_rows', 'bill_jitt_invoice_summary', 'BILLING: invoice fo sorok.'),
                ('jitt_invoice_route_rows', 'bill_jitt_invoice_routes', 'BILLING: invoice route sorok.'),
                ('jitt_invoice_final_routes', 'bill_jitt_invoice_final_routes', 'BILLING: vegleges route elszamolas.'),
                ('jitt_invoice_bonus_routes', 'bill_jitt_invoice_bonus_routes', 'BILLING: bonusz route sorok.'),
                ('jitt_invoice_penalties', 'bill_jitt_invoice_penalties', 'BILLING: buntetesek.'),
                ('jitt_invoice_contract_bonus_rules', 'bill_jitt_contract_bonus_rules', 'BILLING CONFIG: szerzodeses bonusz szabalyok.'),

                ('dsp_day_rates', 'cfg_dsp_day_rates', 'CONFIG: nap tipus dijak.'),
                ('dsp_bonus_rates', 'cfg_dsp_bonus_rates', 'CONFIG: keses es turamegfeleles bonusz dijak.'),
                ('dsp_band_rates', 'cfg_dsp_band_rates', 'CONFIG: savos dijak.'),

                ('discord_route_notifications', 'ops_discord_route_notifications', 'OPS: Discord route ertesitesek.'),
                ('peopleforce_documents', 'ops_peopleforce_documents', 'OPS: PeopleForce dokumentumok.'),
                ('peopleforce_complaints', 'ops_peopleforce_complaints', 'OPS: PeopleForce reklamaciok.'),
                ('peopleforce_card_statuses', 'ops_peopleforce_card_statuses', 'OPS: futar/admin visszajelzo lampak.')
        ) as aliases(old_name, new_name, description)
    loop
        source_kind := null;
        target_kind := null;

        select c.relkind::text
        into source_kind
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relname = item.old_name;

        select c.relkind::text
        into target_kind
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public'
          and c.relname = item.new_name;

        if target_kind = 'v' then
            execute format('drop view public.%I', item.new_name);
            raise notice 'Dropped old alias view public.%', item.new_name;
            target_kind := null;
        end if;

        if target_kind in ('r', 'p') then
            raise notice 'Skip %. Target table public.% already exists.', item.old_name, item.new_name;
            continue;
        end if;

        if source_kind is null then
            raise notice 'Skip %. Source table public.% does not exist.', item.new_name, item.old_name;
            continue;
        end if;

        if source_kind = 'v' then
            raise notice 'Skip %. Source public.% is a view, not a table.', item.new_name, item.old_name;
            continue;
        end if;

        if source_kind not in ('r', 'p') then
            raise notice 'Skip %. Source public.% is relkind=%.', item.new_name, item.old_name, source_kind;
            continue;
        end if;

        execute format(
            'alter table public.%I rename to %I',
            item.old_name,
            item.new_name
        );

        execute format(
            'comment on table public.%I is %L',
            item.new_name,
            item.description || ' Renamed from public.' || item.old_name || '.'
        );

        raise notice 'Renamed public.% -> public.%', item.old_name, item.new_name;
    end loop;
end $$;
