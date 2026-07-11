comment on table public.courier_master is
'CORE: futartorzzs. Courier ID, nev, email, telefon, raktar es kesobb bovitheto torzsadatok.';

comment on table public.dsp_driver_detail_raw is
'RAW: DSP fetch-drivers-detail napi/multbeli JSON snapshotok. Alap a route, customer es statisztika epiteshez.';

comment on table public.dsp_drivers_live_raw is
'RAW: DSP fetch-drivers live snapshot. Aktualis futar, statusz, auto, homerseklet, km es route allapot.';

comment on table public.dsp_vehicle_assignments is
'RAW: DSP fetch-vehicle-assignments snapshot. Neven alapulo auto es muszak kiosztas.';

comment on table public.dsp_route_km_latest is
'STAGE: live DSP snapshotbol kinyert legutobbi route/km allapot.';

comment on table public.dsp_route_distance_calculated is
'STAGE: koordinatakbol szamolt route tavolsag.';

comment on table public.dsp_order_arrivals is
'STAGE: cimszintu erkezes, idoablak, korai/keso statusz es service tipus.';

comment on table public.dsp_route_delay_statistics is
'STAGE: turaszintu kesesi es teljesitesi statisztika.';

comment on table public.dsp_driver_month_summary is
'MART: futar havi DSP KPI es osszesitett statisztika.';

comment on table public.courier_card_stats is
'MART: Kiflis kartya gyors havi snapshot, Streamlit gyorsitasra.';

comment on table public.giriton_shifts_raw is
'RAW: Giriton robot altal gyujtott muszakok.';

comment on table public.giriton_attendance_raw is
'RAW: Giriton Attendance robot altal gyujtott be- es kijelentkezes.';

comment on table public.foglalasok_raw is
'RAW: MuszakPro/Foglalasok sheetbol atvett foglalasi adatok.';

comment on table public.discord_route_notifications is
'OPS: route kiosztas Discord ertesitesek es Kiflis utam betoltes alapja.';

comment on table public.peopleforce_documents is
'OPS: PeopleForce dokumentumok, havi futar dokumentum kezeles.';

comment on table public.peopleforce_complaints is
'OPS: PeopleForce reklamaciok.';

comment on table public.peopleforce_card_statuses is
'OPS: admin/futar visszajelzo lampa dokumentum, task es reklamacio allapotokra.';

comment on table public.jitt_invoice_performance_bud1_raw is
'BILLING RAW: Courier Hub performance couriers API nyers valasz, BUD1.';

comment on table public.jitt_invoice_performance_bud2_raw is
'BILLING RAW: Courier Hub performance couriers API nyers valasz, BUD2.';

comment on view public.jitt_invoice_performance_raw_all is
'BILLING RAW VIEW: BUD1 es BUD2 Courier Hub performance raw egyesitett nezet.';

comment on table public.jitt_invoice_imports is
'BILLING: JITT invoice import futasok.';

comment on table public.jitt_invoice_summary_rows is
'BILLING: JITT invoice fo/osszesito sorok.';

comment on table public.jitt_invoice_route_rows is
'BILLING: JITT invoice route sorok.';

comment on table public.jitt_invoice_final_routes is
'BILLING: vegleges elszamolasi route sorok.';

comment on table public.jitt_invoice_bonus_routes is
'BILLING: bonusz route sorok.';

comment on table public.jitt_invoice_penalties is
'BILLING: invoice buntetes sorok.';

comment on table public.jitt_invoice_contract_bonus_rules is
'BILLING CONFIG: szerzodeses bonusz szabalyok.';

comment on table public.jitt_workbook_imports is
'BILLING RAW: JITT workbook import futasok.';

comment on table public.jitt_workbook_main_raw is
'BILLING RAW: JITT workbook fo tabla nyers sorok.';

comment on table public.jitt_workbook_detail_raw is
'BILLING RAW: JITT workbook reszletes nyers sorok.';

comment on table public.dsp_day_rates is
'BILLING CONFIG: nap es szolgaltatas tipus alapdijak.';

comment on table public.dsp_bonus_rates is
'BILLING CONFIG: kesedelmi es turamegfelelesi bonusz dijak.';

comment on table public.dsp_band_rates is
'BILLING CONFIG: savonkenti kereseti lehetoseg dijak.';
