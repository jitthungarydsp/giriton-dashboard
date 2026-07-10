"""
DSP statisztikák frissítése PostgreSQL/Supabase adatbázisban.

Fontos elv:
- A public.dsp_driver_detail_raw RAW tábla NEM törlődik.
- A többi táblából sem törlünk adatot.
- Minden frissítés INSERT ... ON CONFLICT DO UPDATE módon történik.

Használat:
1. Telepítés:
   pip install psycopg2-binary python-dotenv

2. Környezeti változó:
   DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME

3. Futtatás:
   python dsp_refresh_statistics.py
"""

import os
import sys
from pathlib import Path
from textwrap import dedent

try:
    import psycopg2
except ImportError:
    print("Hiányzik a psycopg2-binary csomag. Telepítés: pip install psycopg2-binary")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIGURATION_SQL_PATH = PROJECT_ROOT / "docs" / "dsp_configuration_tables_and_seed.sql"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    print("Hiányzik a DATABASE_URL környezeti változó.")
    sys.exit(1)


def read_configuration_sql() -> str:
    if not CONFIGURATION_SQL_PATH.exists():
        return ""

    return CONFIGURATION_SQL_PATH.read_text(encoding="utf-8")

CREATE_TABLES_SQL = dedent("""
create table if not exists public.dsp_order_arrivals (
    work_date date not null,
    driver_id integer not null,
    courier_id text,
    route_id text not null,
    checkpoint_id text not null,
    order_id text,
    position integer,
    address text,
    idoablak_kezdete timestamp,
    idoablak_vege timestamp,
    idoablak text,
    tervezett_erkezes timestamp,
    valos_erkezes timestamp,
    tervhez_kepest_perc integer,
    tervhez_kepest_statusz text,
    idoablak_vegehez_kepest_perc integer,
    idoablakhoz_kepest_statusz text,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    primary key (work_date, driver_id, route_id, checkpoint_id)
);

create table if not exists public.dsp_route_delay_statistics (
    work_date date not null,
    driver_id integer not null,
    route_id text not null,
    orders integer not null,
    keso_rendelesek integer not null,
    korai_rendelesek integer not null,
    nem_idoben_rendelesek integer not null,
    keses_szazalek numeric(10,2),
    korai_szazalek numeric(10,2),
    nem_idoben_szazalek numeric(10,2),
    kesedelmi_kategoria text,
    megfelelesi_kategoria text,
    city_delay_bonus integer,
    city_compliance_bonus integer,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    primary key (work_date, driver_id, route_id)
);

create table if not exists public.dsp_driver_month_summary (
    work_month date not null,
    driver_id integer not null,
    courier_id integer,
    ledolgozott_napok integer,
    hetfo integer,
    kedd integer,
    szerda integer,
    csutortok integer,
    pentek integer,
    szombat integer,
    vasarnap integer,
    kiemelt_napok integer,
    sima_napok integer,
    kor_db integer,
    cim_db integer,
    kor_atlag_naponta numeric(10,2),
    cim_atlag_koronkent numeric(10,2),
    cim_atlag_naponta numeric(10,2),
    keso_rendeles_db integer,
    korai_rendeles_db integer,
    nem_idoben_rendeles_db integer,
    keses_szazalek numeric(10,2),
    korai_szazalek numeric(10,2),
    nem_idoben_szazalek numeric(10,2),
    kesedelmi_kategoria text,
    city_delay_bonus integer,
    megfelelesi_kategoria text,
    city_compliance_bonus integer,
    kiemelt_napok_osszege integer,
    sima_napok_osszege integer,
    alap_osszeg integer,
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    primary key (work_month, driver_id)
);
""")

UPSERT_ORDER_ARRIVALS_SQL = dedent("""
insert into public.dsp_order_arrivals (
    work_date,
    driver_id,
    courier_id,
    route_id,
    checkpoint_id,
    order_id,
    position,
    address,
    idoablak_kezdete,
    idoablak_vege,
    idoablak,
    tervezett_erkezes,
    valos_erkezes,
    tervhez_kepest_perc,
    tervhez_kepest_statusz,
    idoablak_vegehez_kepest_perc,
    idoablakhoz_kepest_statusz,
    updated_at
)
with extracted as (
    select
        r.work_date,
        r.driver_id,
        r.response_json ->> 'courier-id' as courier_id,
        route.value ->> 'id' as route_id,
        checkpoint.value ->> 'id' as checkpoint_id,
        checkpoint.value ->> 'orderId' as order_id,
        nullif(checkpoint.value ->> 'position', '')::integer as position,
        checkpoint.value ->> 'address' as address,
        nullif(checkpoint.value ->> 'deliverSince', '')::timestamptz as deliver_since_utc,
        nullif(checkpoint.value ->> 'deliverTill', '')::timestamptz as deliver_till_utc,
        nullif(checkpoint.value ->> 'plannedArrivalTime', '')::timestamptz as planned_arrival_utc,
        nullif(checkpoint.value ->> 'realArrivalTime', '')::timestamptz as real_arrival_utc
    from public.dsp_driver_detail_raw r
    cross join lateral jsonb_array_elements(coalesce(r.response_json -> 'routes', '[]'::jsonb)) route(value)
    cross join lateral jsonb_array_elements(coalesce(route.value -> 'checkpoints', '[]'::jsonb)) checkpoint(value)
)
select
    work_date,
    driver_id,
    courier_id,
    route_id,
    checkpoint_id,
    order_id,
    position,
    address,
    (deliver_since_utc at time zone 'Europe/Budapest')::timestamp as idoablak_kezdete,
    (deliver_till_utc at time zone 'Europe/Budapest')::timestamp as idoablak_vege,
    to_char(deliver_since_utc at time zone 'Europe/Budapest', 'HH24:MI')
        || ' - ' ||
    to_char(deliver_till_utc at time zone 'Europe/Budapest', 'HH24:MI') as idoablak,
    (planned_arrival_utc at time zone 'Europe/Budapest')::timestamp as tervezett_erkezes,
    (real_arrival_utc at time zone 'Europe/Budapest')::timestamp as valos_erkezes,
    round(extract(epoch from (real_arrival_utc - planned_arrival_utc)) / 60)::integer as tervhez_kepest_perc,
    case
        when real_arrival_utc is null then 'Nincs valós érkezés'
        when planned_arrival_utc is null then 'Nincs tervezett érkezés'
        when real_arrival_utc < planned_arrival_utc then 'Korai'
        when real_arrival_utc = planned_arrival_utc then 'Pontos'
        when real_arrival_utc > planned_arrival_utc then 'Késő'
    end as tervhez_kepest_statusz,
    round(extract(epoch from (real_arrival_utc - deliver_till_utc)) / 60)::integer as idoablak_vegehez_kepest_perc,
    case
        when real_arrival_utc is null then 'Nincs valós érkezés'
        when deliver_since_utc is null or deliver_till_utc is null then 'Nincs időablak'
        when real_arrival_utc < deliver_since_utc then 'Korai'
        when real_arrival_utc between deliver_since_utc and deliver_till_utc then 'Időben'
        when real_arrival_utc > deliver_till_utc then 'Késő'
    end as idoablakhoz_kepest_statusz,
    now() as updated_at
from extracted
where route_id is not null
  and checkpoint_id is not null
on conflict (work_date, driver_id, route_id, checkpoint_id)
do update set
    courier_id = excluded.courier_id,
    order_id = excluded.order_id,
    position = excluded.position,
    address = excluded.address,
    idoablak_kezdete = excluded.idoablak_kezdete,
    idoablak_vege = excluded.idoablak_vege,
    idoablak = excluded.idoablak,
    tervezett_erkezes = excluded.tervezett_erkezes,
    valos_erkezes = excluded.valos_erkezes,
    tervhez_kepest_perc = excluded.tervhez_kepest_perc,
    tervhez_kepest_statusz = excluded.tervhez_kepest_statusz,
    idoablak_vegehez_kepest_perc = excluded.idoablak_vegehez_kepest_perc,
    idoablakhoz_kepest_statusz = excluded.idoablakhoz_kepest_statusz,
    updated_at = now();
""")

UPSERT_ROUTE_DELAY_SQL = dedent("""
insert into public.dsp_route_delay_statistics (
    work_date,
    driver_id,
    route_id,
    orders,
    keso_rendelesek,
    korai_rendelesek,
    nem_idoben_rendelesek,
    keses_szazalek,
    korai_szazalek,
    nem_idoben_szazalek,
    kesedelmi_kategoria,
    megfelelesi_kategoria,
    city_delay_bonus,
    city_compliance_bonus,
    updated_at
)
with route_stats as (
    select
        work_date,
        driver_id,
        route_id,
        count(*) as orders,
        count(*) filter (where idoablakhoz_kepest_statusz = 'Késő') as keso_rendelesek,
        count(*) filter (where idoablakhoz_kepest_statusz = 'Korai') as korai_rendelesek,
        count(*) filter (where idoablakhoz_kepest_statusz in ('Késő', 'Korai')) as nem_idoben_rendelesek
    from public.dsp_order_arrivals
    group by work_date, driver_id, route_id
),
calc as (
    select
        *,
        round(keso_rendelesek::numeric / nullif(orders, 0) * 100, 2) as keses_szazalek,
        round(korai_rendelesek::numeric / nullif(orders, 0) * 100, 2) as korai_szazalek,
        round(nem_idoben_rendelesek::numeric / nullif(orders, 0) * 100, 2) as nem_idoben_szazalek
    from route_stats
)
select
    work_date,
    driver_id,
    route_id,
    orders,
    keso_rendelesek,
    korai_rendelesek,
    nem_idoben_rendelesek,
    keses_szazalek,
    korai_szazalek,
    nem_idoben_szazalek,
    case
        when keses_szazalek <= 1.5 then 'Késedelmi-1'
        when keses_szazalek <= 3 then 'Késedelmi-2'
        when keses_szazalek <= 5 then 'Késedelmi-3'
        else 'Nincs késedelmi bónusz'
    end as kesedelmi_kategoria,
    case
        when nem_idoben_szazalek <= 1.5 then 'Megfelelési-1'
        when nem_idoben_szazalek <= 4 then 'Megfelelési-2'
        when nem_idoben_szazalek <= 10 then 'Megfelelési-3'
        else 'Nincs megfelelési bónusz'
    end as megfelelesi_kategoria,
    case
        when keses_szazalek <= 1.5 then 3000
        when keses_szazalek <= 3 then 1000
        when keses_szazalek <= 5 then 500
        else 0
    end as city_delay_bonus,
    case
        when nem_idoben_szazalek <= 1.5 then 3000
        when nem_idoben_szazalek <= 4 then 1000
        when nem_idoben_szazalek <= 10 then 500
        else 0
    end as city_compliance_bonus,
    now() as updated_at
from calc
on conflict (work_date, driver_id, route_id)
do update set
    orders = excluded.orders,
    keso_rendelesek = excluded.keso_rendelesek,
    korai_rendelesek = excluded.korai_rendelesek,
    nem_idoben_rendelesek = excluded.nem_idoben_rendelesek,
    keses_szazalek = excluded.keses_szazalek,
    korai_szazalek = excluded.korai_szazalek,
    nem_idoben_szazalek = excluded.nem_idoben_szazalek,
    kesedelmi_kategoria = excluded.kesedelmi_kategoria,
    megfelelesi_kategoria = excluded.megfelelesi_kategoria,
    city_delay_bonus = excluded.city_delay_bonus,
    city_compliance_bonus = excluded.city_compliance_bonus,
    updated_at = now();
""")

UPSERT_DRIVER_MONTH_SQL = dedent("""
insert into public.dsp_driver_month_summary (
    work_month,
    driver_id,
    courier_id,
    ledolgozott_napok,
    hetfo,
    kedd,
    szerda,
    csutortok,
    pentek,
    szombat,
    vasarnap,
    kiemelt_napok,
    sima_napok,
    kor_db,
    cim_db,
    kor_atlag_naponta,
    cim_atlag_koronkent,
    cim_atlag_naponta,
    keso_rendeles_db,
    korai_rendeles_db,
    nem_idoben_rendeles_db,
    keses_szazalek,
    korai_szazalek,
    nem_idoben_szazalek,
    kesedelmi_kategoria,
    city_delay_bonus,
    megfelelesi_kategoria,
    city_compliance_bonus,
    kiemelt_napok_osszege,
    sima_napok_osszege,
    alap_osszeg,
    updated_at
)
with summary as (
    select
        date_trunc('month', work_date)::date as work_month,
        driver_id,
        max(nullif(courier_id, '')::integer) as courier_id,
        count(distinct work_date) as ledolgozott_napok,
        count(distinct work_date) filter (where extract(isodow from work_date) = 1) as hetfo,
        count(distinct work_date) filter (where extract(isodow from work_date) = 2) as kedd,
        count(distinct work_date) filter (where extract(isodow from work_date) = 3) as szerda,
        count(distinct work_date) filter (where extract(isodow from work_date) = 4) as csutortok,
        count(distinct work_date) filter (where extract(isodow from work_date) = 5) as pentek,
        count(distinct work_date) filter (where extract(isodow from work_date) = 6) as szombat,
        count(distinct work_date) filter (where extract(isodow from work_date) = 7) as vasarnap,
        count(distinct work_date) filter (where extract(isodow from work_date) in (1,4,5,6)) as kiemelt_napok,
        count(distinct work_date) filter (where extract(isodow from work_date) in (2,3,7)) as sima_napok,
        count(distinct route_id) as kor_db,
        count(order_id) as cim_db,
        count(order_id) filter (where idoablakhoz_kepest_statusz = 'Késő') as keso_rendeles_db,
        count(order_id) filter (where idoablakhoz_kepest_statusz = 'Korai') as korai_rendeles_db,
        count(order_id) filter (where idoablakhoz_kepest_statusz in ('Korai', 'Késő')) as nem_idoben_rendeles_db
    from public.dsp_order_arrivals
    group by date_trunc('month', work_date)::date, driver_id
),
calc as (
    select
        *,
        round(kor_db::numeric / nullif(ledolgozott_napok, 0), 2) as kor_atlag_naponta,
        round(cim_db::numeric / nullif(kor_db, 0), 2) as cim_atlag_koronkent,
        round(cim_db::numeric / nullif(ledolgozott_napok, 0), 2) as cim_atlag_naponta,
        round(keso_rendeles_db::numeric / nullif(cim_db, 0) * 100, 2) as keses_szazalek,
        round(korai_rendeles_db::numeric / nullif(cim_db, 0) * 100, 2) as korai_szazalek,
        round(nem_idoben_rendeles_db::numeric / nullif(cim_db, 0) * 100, 2) as nem_idoben_szazalek
    from summary
)
select
    work_month,
    driver_id,
    courier_id,
    ledolgozott_napok,
    hetfo,
    kedd,
    szerda,
    csutortok,
    pentek,
    szombat,
    vasarnap,
    kiemelt_napok,
    sima_napok,
    kor_db,
    cim_db,
    kor_atlag_naponta,
    cim_atlag_koronkent,
    cim_atlag_naponta,
    keso_rendeles_db,
    korai_rendeles_db,
    nem_idoben_rendeles_db,
    keses_szazalek,
    korai_szazalek,
    nem_idoben_szazalek,
    case
        when keses_szazalek <= 1.5 then 'Késedelmi-1'
        when keses_szazalek <= 3 then 'Késedelmi-2'
        when keses_szazalek <= 5 then 'Késedelmi-3'
        else 'Nincs késedelmi bónusz'
    end as kesedelmi_kategoria,
    case
        when keses_szazalek <= 1.5 then 3000
        when keses_szazalek <= 3 then 1000
        when keses_szazalek <= 5 then 500
        else 0
    end as city_delay_bonus,
    case
        when nem_idoben_szazalek <= 1.5 then 'Megfelelési-1'
        when nem_idoben_szazalek <= 4 then 'Megfelelési-2'
        when nem_idoben_szazalek <= 10 then 'Megfelelési-3'
        else 'Nincs megfelelési bónusz'
    end as megfelelesi_kategoria,
    case
        when nem_idoben_szazalek <= 1.5 then 3000
        when nem_idoben_szazalek <= 4 then 1000
        when nem_idoben_szazalek <= 10 then 500
        else 0
    end as city_compliance_bonus,
    kiemelt_napok * 13000 as kiemelt_napok_osszege,
    sima_napok * 11000 as sima_napok_osszege,
    (kiemelt_napok * 13000) + (sima_napok * 11000) as alap_osszeg,
    now() as updated_at
from calc
on conflict (work_month, driver_id)
do update set
    courier_id = excluded.courier_id,
    ledolgozott_napok = excluded.ledolgozott_napok,
    hetfo = excluded.hetfo,
    kedd = excluded.kedd,
    szerda = excluded.szerda,
    csutortok = excluded.csutortok,
    pentek = excluded.pentek,
    szombat = excluded.szombat,
    vasarnap = excluded.vasarnap,
    kiemelt_napok = excluded.kiemelt_napok,
    sima_napok = excluded.sima_napok,
    kor_db = excluded.kor_db,
    cim_db = excluded.cim_db,
    kor_atlag_naponta = excluded.kor_atlag_naponta,
    cim_atlag_koronkent = excluded.cim_atlag_koronkent,
    cim_atlag_naponta = excluded.cim_atlag_naponta,
    keso_rendeles_db = excluded.keso_rendeles_db,
    korai_rendeles_db = excluded.korai_rendeles_db,
    nem_idoben_rendeles_db = excluded.nem_idoben_rendeles_db,
    keses_szazalek = excluded.keses_szazalek,
    korai_szazalek = excluded.korai_szazalek,
    nem_idoben_szazalek = excluded.nem_idoben_szazalek,
    kesedelmi_kategoria = excluded.kesedelmi_kategoria,
    city_delay_bonus = excluded.city_delay_bonus,
    megfelelesi_kategoria = excluded.megfelelesi_kategoria,
    city_compliance_bonus = excluded.city_compliance_bonus,
    kiemelt_napok_osszege = excluded.kiemelt_napok_osszege,
    sima_napok_osszege = excluded.sima_napok_osszege,
    alap_osszeg = excluded.alap_osszeg,
    updated_at = now();
""")

CHECK_SQL = dedent("""
select 'dsp_driver_detail_raw' as tabla, count(*) as sorok from public.dsp_driver_detail_raw
union all
select 'dsp_order_arrivals', count(*) from public.dsp_order_arrivals
union all
select 'dsp_route_delay_statistics', count(*) from public.dsp_route_delay_statistics
union all
select 'dsp_driver_month_summary', count(*) from public.dsp_driver_month_summary;
""")


def run_sql(cursor, name: str, sql: str) -> None:
    print(f"Fut: {name}...")
    cursor.execute(sql)
    print(f"Kész: {name}")


def main() -> None:
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            configuration_sql = read_configuration_sql()

            if configuration_sql:
                run_sql(
                    cur,
                    "DSP konfiguracios tablak es seed adatok",
                    configuration_sql,
                )
            else:
                run_sql(cur, "tablak letrehozasa", CREATE_TABLES_SQL)

            run_sql(cur, "dsp_order_arrivals upsert", UPSERT_ORDER_ARRIVALS_SQL)
            run_sql(cur, "dsp_route_delay_statistics upsert", UPSERT_ROUTE_DELAY_SQL)
            run_sql(cur, "dsp_driver_month_summary upsert", UPSERT_DRIVER_MONTH_SQL)
            conn.commit()

            cur.execute(CHECK_SQL)
            print("\nEllenőrzés:")
            for table_name, row_count in cur.fetchall():
                print(f"- {table_name}: {row_count} sor")


if __name__ == "__main__":
    main()
