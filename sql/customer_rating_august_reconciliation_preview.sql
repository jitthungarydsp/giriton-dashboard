-- Read-only reconciliation. August actual routes vs supplied September corrections.
-- Ratings are from JITT_courier_ratings_2026-08 (1).csv.
with ratings(courier_id, august_rating) as (values
    ('2875', 4.929),
    ('5709', 4.688),
    ('5774', 4.882),
    ('5838', 4.783),
    ('6206', 4.895),
    ('6498', 4.908),
    ('6544', 4.925),
    ('6572', 4.938),
    ('6596', 4.892),
    ('6686', 4.856),
    ('6729', 4.889),
    ('6730', 4.867),
    ('6825', 4.883),
    ('6855', 4.897),
    ('6856', 4.955),
    ('6909', 4.917),
    ('6956', 4.885),
    ('6959', 4.812),
    ('7018', 4.708),
    ('7056', 4.934),
    ('7103', 4.870),
    ('7147', 4.925),
    ('7226', 4.910),
    ('7239', 4.938),
    ('7244', 4.948),
    ('7245', 4.864),
    ('7267', 5.000),
    ('7296', 4.881),
    ('7440', 4.781),
    ('7486', 4.925),
    ('7538', 4.602),
    ('7624', 4.821),
    ('7632', 4.901),
    ('7644', 4.857),
    ('7665', 4.894),
    ('7688', 4.917),
    ('7724', 4.957),
    ('7725', 4.929),
    ('7753', 4.813),
    ('7767', 4.836),
    ('7814', 4.910),
    ('7817', 4.838),
    ('7829', 4.750),
    ('7842', 4.902),
    ('7895', 4.278),
    ('7956', 5.000),
    ('7979', 4.932),
    ('8001', 4.886),
    ('8031', 4.946),
    ('8054', 4.882),
    ('8185', 4.917),
    ('8223', 4.940),
    ('8226', 4.709),
    ('8264', 4.908),
    ('8266', 4.563),
    ('8267', 4.915),
    ('8332', 4.905),
    ('8530', 4.815),
    ('8532', 4.933),
    ('8706', 4.900)
), recorded(courier_id, courier_name, paid_routes, paid_huf, recorded_rate) as (values
    ('6498', 'Abonyi György', 47, 23500, 500),
    ('6956', 'Árva Tamás', 52, 15600, 300),
    ('6909', 'Bajorhegyi Ádám', 51, 25500, 500),
    ('6959', 'Bárándi Bendegúz', 57, 17100, 300),
    ('7056', 'Baranyi Szabolcs', 32, 16000, 500),
    ('8226', 'Baráth 8226 Dominik', 22, 3300, 150),
    ('7267', 'Bodonyi Gellért', 15, 7500, 500),
    ('7226', 'Bubán Szimonetta', 42, 21000, 500),
    ('7842', 'Fabó Marcell', 46, 23000, 500),
    ('7814', 'Farkas Zsolt', 54, 27000, 500),
    ('8530', 'György 8530 Roland', 48, 14400, 300),
    ('8332', 'Hegedüs 8332 Dávid', 50, 25000, 500),
    ('6206', 'Hervai Olivér', 44, 13200, 300),
    ('7829', 'Hohmann András Ármin', 29, 4350, 150),
    ('7147', 'Horváth István', 55, 27500, 500),
    ('6730', 'Jamal Nasir', 37, 11100, 300),
    ('7979', 'Jeney 7979 Tibor', 29, 14500, 500),
    ('7688', 'Kancsár Zoltán', 69, 34500, 500),
    ('7767', 'Kanyó Krisztián', 38, 11400, 300),
    ('6856', 'Király Dániel Dávid', 21, 10500, 500),
    ('7245', 'Kiss 7245 Csaba', 45, 13500, 300),
    ('6544', 'Kiss Koppány Zalán', 18, 9000, 500),
    ('8185', 'Komjáti 8185 Ákos', 65, 32500, 500),
    ('7665', 'Koncsik Zoltán', 39, 11700, 300),
    ('8267', 'Laukó 8267 Buda', 28, 14000, 500),
    ('8001', 'Lulaj 8001 Brendon', 32, 9600, 300),
    ('6686', 'Magyar Csilla', 40, 12000, 300),
    ('7018', 'Mocsáry Attila', 7, 1050, 150),
    ('7724', 'Molnár Ákos', 20, 10000, 500),
    ('7244', 'Nagy 7244 Attila', 19, 9500, 500),
    ('7725', 'Nagy 7725 István', 44, 22000, 500),
    ('8532', 'Nagy 8532 Norbert', 1, 500, 500),
    ('6596', 'Nagy Kristóf', 55, 16500, 300),
    ('7486', 'Papp 7486 Nikolett', 46, 23000, 500),
    ('5838', 'Pardi Ottó', 69, 10350, 150),
    ('7296', 'Petrik Róbert', 25, 7500, 300),
    ('5774', 'Prantner Péter Ákos', 23, 6900, 300),
    ('2875', 'Rácz Csaba', 66, 33000, 500),
    ('7624', 'Révbíró Gábor', 3, 900, 300),
    ('8264', 'Rusvai 8264 Marcell', 28, 14000, 500),
    ('8054', 'Szombati 8054 Márk', 19, 5700, 300),
    ('8223', 'Takács 8223 Attila', 26, 13000, 500),
    ('7632', 'Tinger József', 39, 19500, 500),
    ('7753', 'Tuza Ádám', 28, 8400, 300),
    ('6855', 'Vándor Balázs', 36, 10800, 300),
    ('7817', 'Varecza Roland', 47, 14100, 300)
), august as (
    select distinct on (courier_id) courier_id, driver_name, route_count
    from settlement.courier_settlement_summary
    where period_start >= date '2026-08-01' and period_start < date '2026-09-01'
      and nullif(courier_id, '') is not null
    order by courier_id, calculated_at desc nulls last, session_id desc
), names as (
    select courier_id::text as courier_id, max(courier_name) as courier_name
    from public.courier_master group by courier_id::text
), identities as (
    select courier_id from ratings union select courier_id from recorded union select courier_id from august
)
select
    i.courier_id as "Futár ID",
    coalesce(p.courier_name, a.driver_name, n.courier_name) as "Futár",
    a.route_count as "Augusztusi tényleges körök",
    p.paid_routes as "Korrekcióban rögzített körök",
    a.route_count - coalesce(p.paid_routes, 0) as "Körök különbözete",
    r.august_rating as "Augusztusi értékelés",
    coalesce(p.paid_huf, 0) as "Rögzített korrekció (Ft)",
    p.recorded_rate as "Korábbi korrekció Ft/kör",
    case when a.courier_id is null then 'Hiányzó augusztusi körszám'
         when r.courier_id is null then 'Hiányzó augusztusi értékelés'
         when p.courier_id is null then 'Nincs a kapott korrekciós listában'
         else 'Összevethető' end as "Ellenőrzés"
from identities i
left join august a on a.courier_id = i.courier_id
left join ratings r on r.courier_id = i.courier_id
left join recorded p on p.courier_id = i.courier_id
left join names n on n.courier_id = i.courier_id
order by "Futár", i.courier_id;
