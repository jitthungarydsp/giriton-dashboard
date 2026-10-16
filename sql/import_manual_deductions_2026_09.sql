-- A megadott levonasok felvetele a 2026. szeptemberi kezi korrekciok koze.
-- Az amount_huf pozitiv: a manual_correction_deduction tipus vonja le az osszeget.
-- A lekerdezes ujrafuttathato, a mar letezo azonos tetelt nem duplazza.

with input_rows (source_key, courier_id, adjustment_type, amount_huf, note) as (
    values
        ('manual_deduction:2026-09:7688:625000:javitas', '7688', 'manual_correction_deduction', 625000, 'Levonás | JAVÍTÁSI KÖLTSÉG (NEM CASCO-S KÁR)'),
        ('manual_deduction:2026-09:5774:25000:muszak_2', '5774', 'manual_correction_deduction', 25000, 'Büntetés | 2026.- Műszakról késik 2. eset (5-15 perc)'),
        ('manual_deduction:2026-09:7842:45000:telefon_2025', '7842', 'manual_correction_deduction', 45000, 'Levonás | Telefon/Terminál/PDA sérülése - 2025.'),
        ('manual_deduction:2026-09:7538:15000:korai_40', '7538', 'manual_correction_deduction', 15000, 'Büntetés | Korai érkezés normál 15 perc türelmi idő: 40 percet meghaladó /panasz esetén/'),
        ('manual_deduction:2026-09:6596:24280:parkolas', '6596', 'manual_correction_deduction', 24280, 'Levonás | Szabálysértési / Közigazgatási / Parkolási bírság.'),
        ('manual_deduction:2026-09:7725:50000:parkolas', '7725', 'manual_correction_deduction', 50000, 'Levonás | Szabálysértési / Közigazgatási / Parkolási bírság.'),
        ('manual_deduction:2026-09:8054:nem_jelenik', '8054', 'manual_correction_deduction', 65000, 'Büntetés | Nem jelenik meg teljesítésre -2024.'),
        ('manual_deduction:2026-09:7725:45000:telefon_2025', '7725', 'manual_correction_deduction', 45000, 'Levonás | Telefon/Terminál/PDA sérülése - 2025.'),
        ('manual_deduction:2026-09:7624:45000:telefon_2025', '7624', 'manual_correction_deduction', 45000, 'Levonás | Telefon/Terminál/PDA sérülése - 2025.'),
        ('manual_deduction:2026-09:8223:25000:taska', '8223', 'manual_correction_deduction', 25000, 'Levonás | Táska elvesztése'),
        ('manual_deduction:2026-09:7538:30000:parkolas', '7538', 'manual_correction_deduction', 30000, 'Levonás | Szabálysértési / Közigazgatási / Parkolási bírság.'),
        ('manual_deduction:2026-09:5836:10000:gongyoleg', '5836', 'manual_correction_deduction', 10000, 'Büntetés | Nem megfelelő göngyöleg kezelés + DRS zsák'),
        ('manual_deduction:2026-09:7842:20000:muszak_2', '7842', 'manual_correction_deduction', 20000, 'Büntetés | 2026.- Műszakról késik 2. eset (5-15 perc)'),
        ('manual_deduction:2026-09:7147:25000:taska', '7147', 'manual_correction_deduction', 25000, 'Levonás | Táska elvesztése'),
        ('manual_deduction:2026-09:7842:20000:muszak_1', '7842', 'manual_correction_deduction', 20000, 'Büntetés | 2026.- Műszakról késik 1. eset (5-15 perc)'),
        ('manual_deduction:2026-09:8226:20000:muszak_1', '8226', 'manual_correction_deduction', 20000, 'Büntetés | 2026.- Műszakról késik 1. eset (5-15 perc)'),
        ('manual_deduction:2026-09:7842:25000:taska', '7842', 'manual_correction_deduction', 25000, 'Levonás | Táska elvesztése'),
        ('manual_deduction:2026-09:6544:29955:parkolas', '6544', 'manual_correction_deduction', 29955, 'Levonás | Szabálysértési / Közigazgatási / Parkolási bírság.'),
        ('manual_deduction:2026-09:8223:45000:telefon', '8223', 'manual_correction_deduction', 45000, 'Levonás | Telefon/Terminál/PDA sérülése'),
        ('manual_deduction:2026-09:7226:65000:nem_jelenik', '7226', 'manual_correction_deduction', 65000, 'Büntetés | Nem jelenik meg teljesítésre -2024.'),
        ('manual_deduction:2026-09:7817:25000:taska', '7817', 'manual_correction_deduction', 25000, 'Levonás | Táska elvesztése'),
        ('manual_deduction:2026-09:7817:65000:nem_jelenik', '7817', 'manual_correction_deduction', 65000, 'Büntetés | Nem jelenik meg teljesítésre -2024.'),
        ('manual_deduction:2026-09:6959:65000:nem_jelenik', '6959', 'manual_correction_deduction', 65000, 'Büntetés | Nem jelenik meg teljesítésre -2024.'),
        ('manual_deduction:2026-09:8863:30000:korai_premium', '8863', 'manual_correction_deduction', 30000, 'Levonás | Korai érkezés prémium (1 órás prémium is) 5 perc türelmi idő: 25 percet meghaladó'),
        ('manual_deduction:2026-09:6686:500000:javitas', '6686', 'manual_correction_deduction', 500000, 'Levonás | JAVÍTÁSI KÖLTSÉG (NEM CASCO-S KÁR)'),
        ('manual_deduction:2026-09:8530:25000:taska', '8530', 'manual_correction_deduction', 25000, 'Levonás | Táska elvesztése'),
        ('manual_deduction:2026-09:5774:65000:nem_jelenik', '5774', 'manual_correction_deduction', 65000, 'Büntetés | Nem jelenik meg teljesítésre -2024.'),
        ('manual_deduction:2026-09:5774:20000:muszak_1', '5774', 'manual_correction_deduction', 20000, 'Büntetés | 2026.- Műszakról késik 1. eset (5-15 perc)'),
        ('manual_deduction:2026-09:7688:1512911:sed126', '7688', 'manual_correction_deduction', 1512911, 'Levonás | SED126-több (3) sérülése, anyag, munkadíj, pótlás költsége'),
        ('manual_deduction:2026-09:7226:500000:utkozes', '7226', 'manual_correction_deduction', 500000, 'Levonás | SIW-944, FÁVAL ÜTKÖZÉS'),
        ('manual_deduction:2026-09:7226:409900:sed126', '7226', 'manual_correction_deduction', 409900, 'Levonás | SED-126 felütés, elöl'),
        ('manual_deduction:2026-09:7842:281962:sed126', '7842', 'manual_correction_deduction', 281962, 'Levonás | SED-126, hátsó lökhárító törése')
),
inserted as (
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
        i.courier_id,
        i.adjustment_type,
        i.amount_huf,
        date '2026-09-01',
        date '2026-09-01',
        date '2026-09-30',
        i.source_key,
        i.note,
        'manual-import-2026-09'
    from input_rows i
    where not exists (
        select 1
        from settlement.courier_settlement_adjustment a
        where a.courier_id = i.courier_id
          and a.amount_huf = i.amount_huf
          and a.adjustment_type in ('manual_correction_deduction', 'correction_deduction', 'malus', 'other_expense')
          and lower(trim(regexp_replace(coalesce(a.note, ''), '^(Büntetés|Levonás)\s*\|\s*', ''))) =
              lower(trim(regexp_replace(i.note, '^(Büntetés|Levonás)\s*\|\s*', '')))
          and a.valid_from = date '2026-09-01'
          and coalesce(a.valid_to, date '2026-09-30') = date '2026-09-30'
          and a.deleted_at is null
    )
    returning courier_id, amount_huf, note
)
select
    courier_id,
    amount_huf,
    note
from inserted
order by courier_id, amount_huf, note;
