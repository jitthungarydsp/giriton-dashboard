-- Exact record IDs supplied from the database audit.
-- Only set previously missing end dates; amounts and notes remain unchanged.
update settlement.courier_settlement_adjustment
set valid_to = date '2026-08-31',
    updated_at = now()
where id in (
    'ffc554dd-29b7-4924-9a2f-1c49633f59e0'::uuid,
    '56be7e7f-1c0f-4f8f-95e0-0eeb6689fbfc'::uuid,
    'f758f20f-4f34-4ea5-857e-be81aa20bb0d'::uuid
)
and valid_to is null
returning id, courier_id, adjustment_type, amount_huf, note, valid_from, valid_to;
