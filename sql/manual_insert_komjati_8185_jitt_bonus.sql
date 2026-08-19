begin;

insert into settlement.courier_settlement_adjustment (
    session_id,
    courier_id,
    adjustment_type,
    amount_huf,
    effective_date,
    valid_from,
    valid_to,
    source_key,
    note,
    created_by
)
select
    null,
    '8185',
    'bonus',
    32500,
    date '2026-07-28',
    date '2026-07-01',
    date '2026-07-31',
    'manual_invoice_sheet:S-17872324324:8185:2026-07-28:bonus:32500',
    'Ügyfélértékelés 4,92 | Forrás: manual invoice sheet | Tranzakcio: S-17872324324 | Eredeti név: Komjáti 8185 Ákos',
    'aniko.gizur@jitt.hu'
where not exists (
    select 1
    from settlement.courier_settlement_adjustment
    where courier_id = '8185'
      and adjustment_type = 'bonus'
      and amount_huf = 32500
      and effective_date = date '2026-07-28'
      and coalesce(source_key, '') = 'manual_invoice_sheet:S-17872324324:8185:2026-07-28:bonus:32500'
      and deleted_at is null
);

insert into settlement.courier_settlement_adjustment_event (
    session_id,
    courier_id,
    event_type,
    adjustment_type,
    amount_huf,
    note,
    performed_by
)
select
    null,
    '8185',
    'created',
    'bonus',
    32500,
    'Manuális felvétel: Ügyfélértékelés 4,92 | Tranzakcio: S-17872324324',
    'aniko.gizur@jitt.hu'
where exists (
    select 1
    from settlement.courier_settlement_adjustment
    where courier_id = '8185'
      and adjustment_type = 'bonus'
      and amount_huf = 32500
      and effective_date = date '2026-07-28'
      and coalesce(source_key, '') = 'manual_invoice_sheet:S-17872324324:8185:2026-07-28:bonus:32500'
      and deleted_at is null
)
and not exists (
    select 1
    from settlement.courier_settlement_adjustment_event
    where courier_id = '8185'
      and event_type = 'created'
      and adjustment_type = 'bonus'
      and amount_huf = 32500
      and note = 'Manuális felvétel: Ügyfélértékelés 4,92 | Tranzakcio: S-17872324324'
);

commit;
