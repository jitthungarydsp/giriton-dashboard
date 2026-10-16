-- 2026 szeptemberi ügyfélértékelési kézi korrekciók.
-- A küldött értékelési CSV és körszám-lista alapján előre kiszámolt összegek.
-- A 0 Ft-os futárokhoz nem készül korrekciós sor.

do $$
declare
    item record;
begin
    for item in
        select *
        from (
values
    (null, '2875', 'manual_correction', 33000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:2875', 'Ügyfélértékelés kézi korrekció | 2026-09 | 66 kör | értékelés 4.929 | 500 Ft/kör', 'admin'),
    (null, '5774', 'manual_correction', 6900, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:5774', 'Ügyfélértékelés kézi korrekció | 2026-09 | 23 kör | értékelés 4.882 | 300 Ft/kör', 'admin'),
    (null, '5838', 'manual_correction', 10350, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:5838', 'Ügyfélértékelés kézi korrekció | 2026-09 | 69 kör | értékelés 4.783 | 150 Ft/kör', 'admin'),
    (null, '6206', 'manual_correction', 13200, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6206', 'Ügyfélértékelés kézi korrekció | 2026-09 | 44 kör | értékelés 4.895 | 300 Ft/kör', 'admin'),
    (null, '6498', 'manual_correction', 23500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6498', 'Ügyfélértékelés kézi korrekció | 2026-09 | 47 kör | értékelés 4.908 | 500 Ft/kör', 'admin'),
    (null, '6544', 'manual_correction', 9000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6544', 'Ügyfélértékelés kézi korrekció | 2026-09 | 18 kör | értékelés 4.925 | 500 Ft/kör', 'admin'),
    (null, '6596', 'manual_correction', 16500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6596', 'Ügyfélértékelés kézi korrekció | 2026-09 | 55 kör | értékelés 4.892 | 300 Ft/kör', 'admin'),
    (null, '6686', 'manual_correction', 12000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6686', 'Ügyfélértékelés kézi korrekció | 2026-09 | 40 kör | értékelés 4.856 | 300 Ft/kör', 'admin'),
    (null, '6730', 'manual_correction', 11100, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6730', 'Ügyfélértékelés kézi korrekció | 2026-09 | 37 kör | értékelés 4.867 | 300 Ft/kör', 'admin'),
    (null, '6825', 'manual_correction', 16800, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6825', 'Ügyfélértékelés kézi korrekció | 2026-09 | 56 kör | értékelés 4.883 | 300 Ft/kör', 'admin'),
    (null, '6855', 'manual_correction', 10800, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6855', 'Ügyfélértékelés kézi korrekció | 2026-09 | 36 kör | értékelés 4.897 | 300 Ft/kör', 'admin'),
    (null, '6856', 'manual_correction', 10500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6856', 'Ügyfélértékelés kézi korrekció | 2026-09 | 21 kör | értékelés 4.955 | 500 Ft/kör', 'admin'),
    (null, '6909', 'manual_correction', 25500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6909', 'Ügyfélértékelés kézi korrekció | 2026-09 | 51 kör | értékelés 4.917 | 500 Ft/kör', 'admin'),
    (null, '6956', 'manual_correction', 15600, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6956', 'Ügyfélértékelés kézi korrekció | 2026-09 | 52 kör | értékelés 4.885 | 300 Ft/kör', 'admin'),
    (null, '6959', 'manual_correction', 17100, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:6959', 'Ügyfélértékelés kézi korrekció | 2026-09 | 57 kör | értékelés 4.812 | 300 Ft/kör', 'admin'),
    (null, '7018', 'manual_correction', 1050, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7018', 'Ügyfélértékelés kézi korrekció | 2026-09 | 7 kör | értékelés 4.708 | 150 Ft/kör', 'admin'),
    (null, '7056', 'manual_correction', 16000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7056', 'Ügyfélértékelés kézi korrekció | 2026-09 | 32 kör | értékelés 4.934 | 500 Ft/kör', 'admin'),
    (null, '7147', 'manual_correction', 27500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7147', 'Ügyfélértékelés kézi korrekció | 2026-09 | 55 kör | értékelés 4.925 | 500 Ft/kör', 'admin'),
    (null, '7226', 'manual_correction', 21000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7226', 'Ügyfélértékelés kézi korrekció | 2026-09 | 42 kör | értékelés 4.910 | 500 Ft/kör', 'admin'),
    (null, '7244', 'manual_correction', 9500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7244', 'Ügyfélértékelés kézi korrekció | 2026-09 | 19 kör | értékelés 4.948 | 500 Ft/kör', 'admin'),
    (null, '7245', 'manual_correction', 13500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7245', 'Ügyfélértékelés kézi korrekció | 2026-09 | 45 kör | értékelés 4.864 | 300 Ft/kör', 'admin'),
    (null, '7267', 'manual_correction', 7500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7267', 'Ügyfélértékelés kézi korrekció | 2026-09 | 15 kör | értékelés 5.000 | 500 Ft/kör', 'admin'),
    (null, '7296', 'manual_correction', 7500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7296', 'Ügyfélértékelés kézi korrekció | 2026-09 | 25 kör | értékelés 4.881 | 300 Ft/kör', 'admin'),
    (null, '7486', 'manual_correction', 23000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7486', 'Ügyfélértékelés kézi korrekció | 2026-09 | 46 kör | értékelés 4.925 | 500 Ft/kör', 'admin'),
    (null, '7624', 'manual_correction', 900, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7624', 'Ügyfélértékelés kézi korrekció | 2026-09 | 3 kör | értékelés 4.821 | 300 Ft/kör', 'admin'),
    (null, '7632', 'manual_correction', 19500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7632', 'Ügyfélértékelés kézi korrekció | 2026-09 | 39 kör | értékelés 4.901 | 500 Ft/kör', 'admin'),
    (null, '7665', 'manual_correction', 11700, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7665', 'Ügyfélértékelés kézi korrekció | 2026-09 | 39 kör | értékelés 4.894 | 300 Ft/kör', 'admin'),
    (null, '7688', 'manual_correction', 34500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7688', 'Ügyfélértékelés kézi korrekció | 2026-09 | 69 kör | értékelés 4.917 | 500 Ft/kör', 'admin'),
    (null, '7724', 'manual_correction', 10000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7724', 'Ügyfélértékelés kézi korrekció | 2026-09 | 20 kör | értékelés 4.957 | 500 Ft/kör', 'admin'),
    (null, '7725', 'manual_correction', 22000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7725', 'Ügyfélértékelés kézi korrekció | 2026-09 | 44 kör | értékelés 4.929 | 500 Ft/kör', 'admin'),
    (null, '7753', 'manual_correction', 8400, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7753', 'Ügyfélértékelés kézi korrekció | 2026-09 | 28 kör | értékelés 4.813 | 300 Ft/kör', 'admin'),
    (null, '7767', 'manual_correction', 11400, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7767', 'Ügyfélértékelés kézi korrekció | 2026-09 | 38 kör | értékelés 4.836 | 300 Ft/kör', 'admin'),
    (null, '7814', 'manual_correction', 27000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7814', 'Ügyfélértékelés kézi korrekció | 2026-09 | 54 kör | értékelés 4.910 | 500 Ft/kör', 'admin'),
    (null, '7817', 'manual_correction', 14100, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7817', 'Ügyfélértékelés kézi korrekció | 2026-09 | 47 kör | értékelés 4.838 | 300 Ft/kör', 'admin'),
    (null, '7829', 'manual_correction', 4350, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7829', 'Ügyfélértékelés kézi korrekció | 2026-09 | 29 kör | értékelés 4.750 | 150 Ft/kör', 'admin'),
    (null, '7842', 'manual_correction', 23000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7842', 'Ügyfélértékelés kézi korrekció | 2026-09 | 46 kör | értékelés 4.902 | 500 Ft/kör', 'admin'),
    (null, '7979', 'manual_correction', 14500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:7979', 'Ügyfélértékelés kézi korrekció | 2026-09 | 29 kör | értékelés 4.932 | 500 Ft/kör', 'admin'),
    (null, '8001', 'manual_correction', 9600, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8001', 'Ügyfélértékelés kézi korrekció | 2026-09 | 32 kör | értékelés 4.886 | 300 Ft/kör', 'admin'),
    (null, '8054', 'manual_correction', 5700, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8054', 'Ügyfélértékelés kézi korrekció | 2026-09 | 19 kör | értékelés 4.882 | 300 Ft/kör', 'admin'),
    (null, '8185', 'manual_correction', 32500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8185', 'Ügyfélértékelés kézi korrekció | 2026-09 | 65 kör | értékelés 4.917 | 500 Ft/kör', 'admin'),
    (null, '8223', 'manual_correction', 13000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8223', 'Ügyfélértékelés kézi korrekció | 2026-09 | 26 kör | értékelés 4.940 | 500 Ft/kör', 'admin'),
    (null, '8226', 'manual_correction', 3300, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8226', 'Ügyfélértékelés kézi korrekció | 2026-09 | 22 kör | értékelés 4.709 | 150 Ft/kör', 'admin'),
    (null, '8264', 'manual_correction', 14000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8264', 'Ügyfélértékelés kézi korrekció | 2026-09 | 28 kör | értékelés 4.908 | 500 Ft/kör', 'admin'),
    (null, '8267', 'manual_correction', 14000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8267', 'Ügyfélértékelés kézi korrekció | 2026-09 | 28 kör | értékelés 4.915 | 500 Ft/kör', 'admin'),
    (null, '8332', 'manual_correction', 25000, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8332', 'Ügyfélértékelés kézi korrekció | 2026-09 | 50 kör | értékelés 4.905 | 500 Ft/kör', 'admin'),
    (null, '8530', 'manual_correction', 14400, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8530', 'Ügyfélértékelés kézi korrekció | 2026-09 | 48 kör | értékelés 4.815 | 300 Ft/kör', 'admin'),
    (null, '8532', 'manual_correction', 500, date '2026-09-01', date '2026-09-01', date '2026-09-30', 'customer_rating_manual_2026_09:8532', 'Ügyfélértékelés kézi korrekció | 2026-09 | 1 kör | értékelés 4.933 | 500 Ft/kör', 'admin')
) as source(
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
loop
        update settlement.courier_settlement_adjustment
        set
            adjustment_type = item.adjustment_type,
            amount_huf = item.amount_huf,
            effective_date = item.effective_date,
            valid_from = item.valid_from,
            valid_to = item.valid_to,
            note = item.note,
            created_by = item.created_by,
            updated_at = now(),
            is_active = true,
            deleted_at = null,
            deleted_by = null
        where courier_id = item.courier_id
          and adjustment_type = item.adjustment_type
          and valid_from = item.valid_from
          and valid_to = item.valid_to
          and note = item.note
          and is_active
          and deleted_at is null;

        if not found then
            insert into settlement.courier_settlement_adjustment (
                session_id,
                courier_id,
                adjustment_type,
                amount_huf,
                effective_date,
                valid_from,
                valid_to,
                note,
                created_by
            )
            values (
                item.session_id,
                item.courier_id,
                item.adjustment_type,
                item.amount_huf,
                item.effective_date,
                item.valid_from,
                item.valid_to,
                item.note,
                item.created_by
            );
        end if;
    end loop;
end
$$;
