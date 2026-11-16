-- Futár–hónap szintű folyamat- és pénzügyi adatok minden mentett hónapra.
-- Kapcsolat: courier_metric_id (futár sora) -> summary_id (havi főösszesítő).

select
    courier.period_start as honap,
    courier.courier_month_key as futar_honap_azonosito,
    courier.courier_metric_id as futar_sor_azonosito,
    courier.summary_id as havi_osszesito_azonosito,
    courier.courier_id as futar_id,
    courier.courier_name as futar_nev,
    courier.settlement_opened_at as elszamolas_megnyitva,
    courier.settlement_accepted_at as elszamolas_elfogadva,
    courier.tig_accepted_at as tig_elfogadva,
    courier.invoice_uploaded_at as szamla_feltoltve,
    courier.paid_at as kifizetve,
    courier.opening_to_settlement_hours as megnyitas_elfogadas_ora,
    courier.settlement_to_tig_hours as elfogadas_tig_ora,
    courier.tig_to_invoice_hours as tig_szamla_ora,
    courier.invoice_to_paid_hours as szamla_kifizetes_ora,
    courier.opening_to_paid_hours as teljes_atfutas_ora,
    courier.financial_complaint_count as reklamaciok_szama,
    courier.responded_complaint_count as megvalaszolt_reklamacio,
    courier.response_average_hours as valaszido_atlag_ora,
    courier.malus_huf as malusz_ft,
    courier.other_deductions_huf as egyeb_levonas_ft,
    courier.deductions_huf as levonas_osszesen_ft,
    monthly.completed_flow_count as honap_lezart_folyamatai,
    monthly.complaint_total as honap_reklamacioi,
    monthly.deductions_total_huf as honap_levonasai
from settlement.courier_monthly_process_metric courier
join settlement.monthly_process_metric_summary monthly
    on monthly.summary_id = courier.summary_id
   and monthly.period_start = courier.period_start
order by courier.period_start desc, courier.courier_name asc, courier.courier_id asc;
