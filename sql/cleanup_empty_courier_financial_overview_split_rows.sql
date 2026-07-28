begin;

delete from public.courier_financial_overview_raw_bud1
where jsonb_array_length(coalesce(response_json -> 'routes', '[]'::jsonb)) = 0;

delete from public.courier_financial_overview_raw_bud2
where jsonb_array_length(coalesce(response_json -> 'routes', '[]'::jsonb)) = 0;

commit;
