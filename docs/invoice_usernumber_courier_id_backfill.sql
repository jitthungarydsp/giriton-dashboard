alter table if exists public.bill_jitt_invoice_final_routes
    add column if not exists courier_id text;

alter table if exists public.jitt_invoice_final_routes
    add column if not exists courier_id text;

update public.bill_jitt_invoice_final_routes final
set
    courier_id = nullif(routes.row_data ->> 'USERNUMBER', ''),
    updated_at = now()
from public.bill_jitt_invoice_routes routes
where final.source_name = routes.source_name
  and final.source_spreadsheet_id = routes.source_spreadsheet_id
  and final.worksheet_name = routes.worksheet_name
  and final.row_number = routes.row_number
  and nullif(routes.row_data ->> 'USERNUMBER', '') is not null
  and coalesce(final.courier_id, '') <> nullif(routes.row_data ->> 'USERNUMBER', '');

update public.jitt_invoice_final_routes final
set
    courier_id = nullif(routes.row_data ->> 'USERNUMBER', ''),
    updated_at = now()
from public.jitt_invoice_route_rows routes
where final.source_name = routes.source_name
  and final.source_spreadsheet_id = routes.source_spreadsheet_id
  and final.worksheet_name = routes.worksheet_name
  and final.row_number = routes.row_number
  and nullif(routes.row_data ->> 'USERNUMBER', '') is not null
  and coalesce(final.courier_id, '') <> nullif(routes.row_data ->> 'USERNUMBER', '');
