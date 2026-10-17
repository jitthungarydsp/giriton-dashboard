with targets(courier_id, courier_name, august_routes, recorded_routes,
             august_rating, rate_huf, recorded_huf, difference_huf) as (values
    ('2875', 'Rácz Csaba', 80, 66, 4.929, 500, 33000, 7000),
    ('8185', 'Komjáti 8185 Ákos', 75, 65, 4.917, 500, 32500, 5000),
    ('6596', 'Nagy Kristóf', 64, 55, 4.892, 300, 16500, 2700),
    ('7979', 'Jeney 7979 Tibor', 63, 29, 4.932, 500, 14500, 17000),
    ('7296', 'Petrik Róbert', 63, 25, 4.881, 300, 7500, 11400),
    ('6825', 'Szolnoki Tibor', 62, 0, 4.883, 300, 0, 18600),
    ('8332', 'Hegedüs 8332 Dávid', 55, 50, 4.905, 500, 25000, 2500),
    ('7725', 'Nagy 7725 István', 55, 44, 4.929, 500, 22000, 5500),
    ('6498', 'Abonyi György', 53, 47, 4.908, 500, 23500, 3000),
    ('7226', 'Bubán Szimonetta', 53, 42, 4.910, 500, 21000, 5500),
    ('6206', 'Hervai Olivér', 50, 44, 4.895, 300, 13200, 1800),
    ('7767', 'Kanyó Krisztián', 49, 38, 4.836, 300, 11400, 3300),
    ('7817', 'Varecza Roland', 48, 47, 4.838, 300, 14100, 300),
    ('6686', 'Magyar Csilla', 46, 40, 4.856, 300, 12000, 1800),
    ('7056', 'Baranyi Szabolcs', 43, 32, 4.934, 500, 16000, 5500),
    ('7753', 'Tuza Ádám', 39, 28, 4.813, 300, 8400, 3300),
    ('6856', 'Király Dániel Dávid', 38, 21, 4.955, 500, 10500, 8500),
    ('7103', 'Stumpf András István', 30, 0, 4.870, 300, 0, 9000),
    ('6544', 'Kiss Koppány Zalán', 29, 18, 4.925, 500, 9000, 5500),
    ('7724', 'Molnár Ákos', 29, 20, 4.957, 500, 10000, 4500),
    ('7244', 'Nagy 7244 Attila', 28, 19, 4.948, 500, 9500, 4500),
    ('6572', 'Deme 6572 Tamás', 25, 0, 4.938, 500, 0, 12500),
    ('7018', 'Mocsáry Attila', 15, 7, 4.708, 150, 1050, 1200),
    ('7624', 'Révbíró Gábor', 12, 3, 4.821, 300, 900, 2700),
    ('8031', 'Boskó 8031 György', 10, 0, 4.946, 500, 0, 5000),
    ('7239', 'Gémes Zoltán', 8, 0, 4.938, 500, 0, 4000),
    ('7956', 'Nagy 7956 Gergely', 6, 0, 5.000, 500, 0, 3000),
    ('8532', 'Nagy 8532 Norbert', 5, 1, 4.933, 500, 500, 2000),
    ('8706', 'Péchy 8706 Tamás', 5, 0, 4.900, 500, 0, 2500),
    ('7440', 'Jamal Wasil', 3, 0, 4.781, 150, 0, 450),
    ('7644', 'Gurzó Balázs', 2, 0, 4.857, 300, 0, 600),
    ('6729', 'Zorányi Tamás Bence', 2, 0, 4.889, 300, 0, 600)
), prepared as (
    select t.*, 'rating_catchup_202608_paid_202609:' || t.courier_id as marker,
           e.id as existing_id, e.amount_huf as existing_amount,
           e.is_active as existing_active, e.adjustment_type as existing_type,
           e.valid_from as existing_from, e.valid_to as existing_to,
           coalesce(b.live_amount, 0) as live_amount,
           coalesce(e.session_id, ss.session_id, nullif(trim(cfg.session_id), '')::uuid) as session_ref
    from targets t
    left join settlement.courier_settlement_adjustment e
      on e.source_key = 'rating_catchup_202608_paid_202609:' || t.courier_id
     and e.deleted_at is null
    left join lateral (
        select sum(case when a.adjustment_type in ('correction_deduction','manual_correction_deduction')
                        then -abs(a.amount_huf) else a.amount_huf end) as live_amount
        from settlement.courier_settlement_adjustment a
        where a.courier_id::text=t.courier_id and a.is_active and a.deleted_at is null
          and a.adjustment_type in ('correction','manual_correction','correction_income',
                                    'correction_deduction','manual_correction_deduction')
          and coalesce(a.valid_from,a.effective_date) <= date '2026-09-30'
          and (a.valid_to is null or a.valid_to >= date '2026-09-01')
          and translate(lower(coalesce(a.note,'')), 'áéíóöőúüű','aeiooouuu')
              ~ 'ugyfel[[:space:]-]*ertekel|customer[[:space:]-]*rating'
          and coalesce(a.source_key,'') <> 'rating_catchup_202608_paid_202609:' || t.courier_id
    ) b on true
    left join lateral (
        select session_id from settlement.courier_settlement_summary
        where courier_id::text=t.courier_id and period_start=date '2026-09-01'
        order by calculated_at desc nulls last,session_id desc limit 1
    ) ss on true
    left join lateral (
        select session_id from settlement.mobile_settlement_period_config
        where period_start=date '2026-09-01' limit 1
    ) cfg on true
), checked as (
    select p.*, case
        when existing_id is not null and (
            existing_amount <> difference_huf or not existing_active
            or existing_type <> 'manual_correction'
            or existing_from is distinct from date '2026-09-01'
            or existing_to is distinct from date '2026-09-30'
        ) then 'Eltérő korábbi import'
        when existing_id is null and live_amount <> recorded_huf then 'Megváltozott korábbi korrekcióösszeg'
        when existing_id is null and session_ref is null then 'Hiányzó szeptemberi session_id'
        else null end as problem
    from prepared p
), inserted as (
    insert into settlement.courier_settlement_adjustment (
        session_id,courier_id,adjustment_type,amount_huf,effective_date,
        valid_from,valid_to,source_key,note,is_active,created_by
    )
    select session_ref,courier_id,'manual_correction',difference_huf,date '2026-09-01',
           date '2026-09-01',date '2026-09-30',marker,
           format('Ügyfélértékelés különbözet | 2026-08 | %s | %s kör | korábban %s kör, %s Ft | értékelés %s | %s Ft/kör | pótlás %s Ft',
                  courier_name,august_routes,recorded_routes,recorded_huf,august_rating,rate_huf,difference_huf),
           true,'admin'
    from checked
    where existing_id is null
      and not exists (select 1 from checked where problem is not null)
    on conflict do nothing
    returning id,session_id,courier_id,amount_huf,source_key,note
), audit as (
    insert into settlement.courier_settlement_adjustment_event (
        session_id,courier_id,event_type,adjustment_type,amount_huf,note,performed_by
    )
    select session_id,courier_id,'created','manual_correction',amount_huf,
           'Augusztusi ügyfélértékelési különbözet szeptemberi pótlása. Forrás: ' || source_key,'admin'
    from inserted
    returning id
)
select c.courier_id as "Futár ID", c.courier_name as "Futár",
       c.difference_huf as "Pótlás (Ft)", c.recorded_huf as "Várt korábbi összeg",
       c.live_amount as "DB korábbi összeg",
       case when c.problem is not null then c.problem
            when i.id is not null then 'Importálva'
            when c.existing_id is not null then 'Már korábban importálva'
            when exists (select 1 from checked where problem is not null) then 'Nincs import: másik tételnél eltérés van'
            else 'Nem történt beszúrás; ellenőrizd az ütközést' end as "Eredmény"
from checked c left join inserted i on i.source_key=c.marker
order by c.courier_name;
