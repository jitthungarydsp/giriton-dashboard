do $$
declare
    item record;
begin
    for item in
        select *
        from (
            values
                ('core_couriers', 'courier_master', 'CORE: futartorzzs, courier ID alapu alapadatok.'),

                ('raw_dsp_driver_detail', 'dsp_driver_detail_raw', 'RAW: DSP fetch-drivers-detail nyers JSON.'),
                ('raw_dsp_live_drivers', 'dsp_drivers_live_raw', 'RAW: DSP fetch-drivers live snapshot.'),
                ('raw_dsp_vehicle_assignments', 'dsp_vehicle_assignments', 'RAW: DSP vehicle assignments.'),
                ('raw_giriton_shifts', 'giriton_shifts_raw', 'RAW: Giriton muszak adatok.'),
                ('raw_giriton_attendance', 'giriton_attendance_raw', 'RAW: Giriton be- es kijelentkezes.'),
                ('raw_muszakpro_bookings', 'foglalasok_raw', 'RAW: MuszakPro/Foglalasok adatok.'),
                ('raw_jitt_invoice_perf_bud1', 'jitt_invoice_performance_bud1_raw', 'RAW: Courier Hub performance BUD1.'),
                ('raw_jitt_invoice_perf_bud2', 'jitt_invoice_performance_bud2_raw', 'RAW: Courier Hub performance BUD2.'),
                ('raw_jitt_workbook_imports', 'jitt_workbook_imports', 'RAW: JITT workbook import futasok.'),
                ('raw_jitt_workbook_main', 'jitt_workbook_main_raw', 'RAW: JITT workbook fo tabla.'),
                ('raw_jitt_workbook_detail', 'jitt_workbook_detail_raw', 'RAW: JITT workbook reszletes tabla.'),

                ('stg_dsp_order_arrivals', 'dsp_order_arrivals', 'STAGE: cimszintu erkezes es idoablak bontas.'),
                ('stg_dsp_route_delay', 'dsp_route_delay_statistics', 'STAGE: route keses statisztika.'),
                ('stg_dsp_route_distance', 'dsp_route_distance_calculated', 'STAGE: szamolt route tavolsag.'),
                ('stg_dsp_route_km_latest', 'dsp_route_km_latest', 'STAGE: live km/tura allapot.'),

                ('mart_dsp_driver_month', 'dsp_driver_month_summary', 'MART: havi futar KPI.'),
                ('mart_courier_card_stats', 'courier_card_stats', 'MART: Kiflis kartya gyors statisztika.'),

                ('bill_jitt_invoice_imports', 'jitt_invoice_imports', 'BILLING: invoice import futasok.'),
                ('bill_jitt_invoice_summary', 'jitt_invoice_summary_rows', 'BILLING: invoice fo sorok.'),
                ('bill_jitt_invoice_routes', 'jitt_invoice_route_rows', 'BILLING: invoice route sorok.'),
                ('bill_jitt_invoice_final_routes', 'jitt_invoice_final_routes', 'BILLING: vegleges route elszamolas.'),
                ('bill_jitt_invoice_bonus_routes', 'jitt_invoice_bonus_routes', 'BILLING: bonusz route sorok.'),
                ('bill_jitt_invoice_penalties', 'jitt_invoice_penalties', 'BILLING: buntetesek.'),
                ('bill_jitt_contract_bonus_rules', 'jitt_invoice_contract_bonus_rules', 'BILLING CONFIG: szerzodeses bonusz szabalyok.'),

                ('cfg_dsp_day_rates', 'dsp_day_rates', 'CONFIG: nap tipus dijak.'),
                ('cfg_dsp_bonus_rates', 'dsp_bonus_rates', 'CONFIG: keses es turamegfeleles bonusz dijak.'),
                ('cfg_dsp_band_rates', 'dsp_band_rates', 'CONFIG: savos dijak.'),

                ('ops_discord_route_notifications', 'discord_route_notifications', 'OPS: Discord route ertesitesek.'),
                ('ops_peopleforce_documents', 'peopleforce_documents', 'OPS: PeopleForce dokumentumok.'),
                ('ops_peopleforce_complaints', 'peopleforce_complaints', 'OPS: PeopleForce reklamaciok.'),
                ('ops_peopleforce_card_statuses', 'peopleforce_card_statuses', 'OPS: futar/admin visszajelzo lampak.')
        ) as aliases(alias_name, source_name, description)
    loop
        if to_regclass(format('public.%I', item.source_name)) is null then
            raise notice 'Skip %. Source public.% does not exist.', item.alias_name, item.source_name;
        else
            execute format(
                'create or replace view public.%I as select * from public.%I',
                item.alias_name,
                item.source_name
            );

            execute format(
                'comment on view public.%I is %L',
                item.alias_name,
                item.description || ' Source: public.' || item.source_name || '.'
            );

            raise notice 'Created/updated view public.% -> public.%', item.alias_name, item.source_name;
        end if;
    end loop;
end $$;
