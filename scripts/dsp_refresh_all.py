"""
DSP összesítő / frissítő pipeline.

A script a már eltárolt RAW táblákból építi és frissíti a normalizált,
statisztikai és összesítő táblákat.

Kiinduló RAW táblák:
- public.dsp_driver_detail_raw
- public.dsp_attendance_raw

Frissített táblák:
1. public.dsp_order_arrivals
2. public.dsp_route_delay_statistics
3. public.dsp_driver_month_summary
4. public.dsp_company_kpi_summary
5. public.dsp_attendance_couriers
6. public.dsp_attendance_shifts
7. public.dsp_attendance_routes
8. public.dsp_shift_route_summary

Fontos:
- A script NEM töröl adatot.
- Minden célpont INSERT ... ON CONFLICT DO UPDATE módszerrel frissül.
- A RAW táblákhoz nem nyúl.
- A budapesti időpontokat Europe/Budapest időzónában tárolja.

Telepítés:
    python -m pip install psycopg2-binary python-dotenv

Környezeti változó:
    DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME?sslmode=require

Futtatás:
    python scripts/dsp_refresh_all.py
"""

import os
import sys
from pathlib import Path
from textwrap import dedent
from urllib.parse import urlparse

try:
    import psycopg2
except ImportError:
    print(
        "Hiányzik a psycopg2-binary csomag.\n"
        "Telepítés: python -m pip install psycopg2-binary"
    )
    sys.exit(1)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIGURATION_SQL_PATH = PROJECT_ROOT / "docs" / "dsp_configuration_tables_and_seed.sql"


def get_database_url() -> str:
    value = (
        os.getenv("DATABASE_URL")
        or os.getenv("SUPABASE_DB_URL")
        or ""
    ).strip()

    if not value:
        raise RuntimeError(
            "Hiányzik a DATABASE_URL környezeti változó.\n"
            "Példa:\n"
            "DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DBNAME?sslmode=require"
        )

    if value.startswith("https://supabase.com/dashboard/"):
        raise RuntimeError(
            "A DATABASE_URL jelenleg a Supabase Dashboard címe.\n"
            "Ide PostgreSQL connection string kell, amely postgresql:// vagy postgres:// kezdetű."
        )

    parsed = urlparse(value)

    if parsed.scheme not in {"postgresql", "postgres"}:
        raise RuntimeError(
            "Hibás DATABASE_URL. PostgreSQL URL szükséges, például:\n"
            "postgresql://USER:PASSWORD@HOST:PORT/DBNAME?sslmode=require"
        )

    return value


def read_configuration_sql() -> str:
    if not CONFIGURATION_SQL_PATH.exists():
        return ""

    return CONFIGURATION_SQL_PATH.read_text(encoding="utf-8")


CREATE_TABLES_SQL = dedent(
    """
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

    create table if not exists public.dsp_company_kpi_summary (
        work_month date not null,
        total_orders integer,
        total_routes integer,
        total_drivers integer,
        worked_days integer,
        idoben_db integer,
        idoben_szazalek numeric(10,2),
        korai_db integer,
        korai_szazalek numeric(10,2),
        keso_db integer,
        keso_szazalek numeric(10,2),
        idokapun_kivuli_db integer,
        idokapun_kivuli_szazalek numeric(10,2),
        rendeles_atlag_koronkent numeric(10,2),
        kor_atlag_naponta numeric(10,2),
        rendeles_atlag_naponta numeric(10,2),
        created_at timestamptz default now(),
        updated_at timestamptz default now(),
        primary key (work_month)
    );

    create table if not exists public.dsp_attendance_couriers (
        work_date date not null,
        dsp_id text,
        dsp_name text,
        courier_id integer not null,
        courier_name text,
        warehouse_name text,
        shift_count integer,
        route_count integer,
        created_at timestamptz default now(),
        updated_at timestamptz default now(),
        primary key (work_date, courier_id)
    );

    create table if not exists public.dsp_attendance_shifts (
        work_date date not null,
        dsp_id text,
        dsp_name text,
        courier_id integer not null,
        courier_name text,
        warehouse_name text,
        shift_id bigint not null,
        shift_name text,
        shift_start timestamp,
        shift_end timestamp,
        available_for_shift_since timestamp,
        available_diff_minutes integer,
        availability_status text,
        created_at timestamptz default now(),
        updated_at timestamptz default now(),
        primary key (work_date, courier_id, shift_id)
    );

    create table if not exists public.dsp_attendance_routes (
        work_date date not null,
        dsp_id text,
        dsp_name text,
        courier_id integer not null,
        courier_name text,
        warehouse_name text,
        route_id bigint not null,
        courier_registered_at timestamp,
        assigned_at timestamp,
        planned_departure timestamp,
        real_departure timestamp,
        planned_return timestamp,
        real_return timestamp,
        planned_route_minutes integer,
        real_route_minutes integer,
        departure_diff_minutes integer,
        return_diff_minutes integer,
        departure_status text,
        return_status text,
        created_at timestamptz default now(),
        updated_at timestamptz default now(),
        primary key (work_date, courier_id, route_id)
    );

    create table if not exists public.dsp_shift_route_summary (
        work_date date not null,
        courier_id integer not null,
        courier_name text,
        warehouse_name text,
        shift_id bigint,
        shift_name text,
        shift_start timestamp,
        shift_end timestamp,
        available_for_shift_since timestamp,
        route_id bigint not null,
        courier_registered_at timestamp,
        assigned_at timestamp,
        planned_departure timestamp,
        planned_return timestamp,
        planned_route_minutes integer,
        real_departure timestamp,
        real_return timestamp,
        real_route_minutes integer,
        orders integer,
        keso_rendelesek integer,
        korai_rendelesek integer,
        nem_idoben_rendelesek integer,
        keses_szazalek numeric(10,2),
        korai_szazalek numeric(10,2),
        nem_idoben_szazalek numeric(10,2),
        kesedelmi_kategoria text,
        megfelelesi_kategoria text,
        city_delay_bonus integer,
        city_compliance_bonus integer,
        created_at timestamptz default now(),
        updated_at timestamptz default now(),
        primary key (work_date, courier_id, route_id)
    );

    alter table public.dsp_shift_route_summary
        add column if not exists orders integer,
        add column if not exists keso_rendelesek integer,
        add column if not exists korai_rendelesek integer,
        add column if not exists nem_idoben_rendelesek integer,
        add column if not exists keses_szazalek numeric(10,2),
        add column if not exists korai_szazalek numeric(10,2),
        add column if not exists nem_idoben_szazalek numeric(10,2),
        add column if not exists kesedelmi_kategoria text,
        add column if not exists megfelelesi_kategoria text,
        add column if not exists city_delay_bonus integer,
        add column if not exists city_compliance_bonus integer;
    """
)


UPSERT_ORDER_ARRIVALS_SQL = dedent(
    """
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
        cross join lateral jsonb_array_elements(
            coalesce(r.response_json -> 'routes', '[]'::jsonb)
        ) route(value)
        cross join lateral jsonb_array_elements(
            coalesce(route.value -> 'checkpoints', '[]'::jsonb)
        ) checkpoint(value)
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
        (deliver_since_utc at time zone 'Europe/Budapest')::timestamp,
        (deliver_till_utc at time zone 'Europe/Budapest')::timestamp,
        case
            when deliver_since_utc is null or deliver_till_utc is null then null
            else
                to_char(deliver_since_utc at time zone 'Europe/Budapest', 'HH24:MI')
                || ' - ' ||
                to_char(deliver_till_utc at time zone 'Europe/Budapest', 'HH24:MI')
        end,
        (planned_arrival_utc at time zone 'Europe/Budapest')::timestamp,
        (real_arrival_utc at time zone 'Europe/Budapest')::timestamp,
        round(
            extract(epoch from (real_arrival_utc - planned_arrival_utc)) / 60
        )::integer,
        case
            when real_arrival_utc is null then 'Nincs valós érkezés'
            when planned_arrival_utc is null then 'Nincs tervezett érkezés'
            when real_arrival_utc < planned_arrival_utc then 'Korai'
            when real_arrival_utc = planned_arrival_utc then 'Pontos'
            else 'Késő'
        end,
        round(
            extract(epoch from (real_arrival_utc - deliver_till_utc)) / 60
        )::integer,
        case
            when real_arrival_utc is null then 'Nincs valós érkezés'
            when deliver_since_utc is null or deliver_till_utc is null then 'Nincs időablak'
            when real_arrival_utc < deliver_since_utc then 'Korai'
            when real_arrival_utc between deliver_since_utc and deliver_till_utc then 'Időben'
            else 'Késő'
        end,
        now()
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
    """
)


UPSERT_ROUTE_DELAY_SQL = dedent(
    """
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
            count(*) filter (
                where idoablakhoz_kepest_statusz = 'Késő'
            ) as keso_rendelesek,
            count(*) filter (
                where idoablakhoz_kepest_statusz = 'Korai'
            ) as korai_rendelesek,
            count(*) filter (
                where idoablakhoz_kepest_statusz in ('Késő', 'Korai')
            ) as nem_idoben_rendelesek
        from public.dsp_order_arrivals
        group by work_date, driver_id, route_id
    ),
    calc as (
        select
            *,
            round(keso_rendelesek::numeric / nullif(orders, 0) * 100, 2)
                as keses_szazalek,
            round(korai_rendelesek::numeric / nullif(orders, 0) * 100, 2)
                as korai_szazalek,
            round(nem_idoben_rendelesek::numeric / nullif(orders, 0) * 100, 2)
                as nem_idoben_szazalek
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
        end,
        case
            when nem_idoben_szazalek <= 1.5 then 'Megfelelési-1'
            when nem_idoben_szazalek <= 4 then 'Megfelelési-2'
            when nem_idoben_szazalek <= 10 then 'Megfelelési-3'
            else 'Nincs megfelelési bónusz'
        end,
        case
            when keses_szazalek <= 1.5 then 3000
            when keses_szazalek <= 3 then 1000
            when keses_szazalek <= 5 then 500
            else 0
        end,
        case
            when nem_idoben_szazalek <= 1.5 then 3000
            when nem_idoben_szazalek <= 4 then 1000
            when nem_idoben_szazalek <= 10 then 500
            else 0
        end,
        now()
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
    """
)


UPSERT_DRIVER_MONTH_SQL = dedent(
    """
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
            count(distinct work_date) filter (
                where extract(isodow from work_date) = 1
            ) as hetfo,
            count(distinct work_date) filter (
                where extract(isodow from work_date) = 2
            ) as kedd,
            count(distinct work_date) filter (
                where extract(isodow from work_date) = 3
            ) as szerda,
            count(distinct work_date) filter (
                where extract(isodow from work_date) = 4
            ) as csutortok,
            count(distinct work_date) filter (
                where extract(isodow from work_date) = 5
            ) as pentek,
            count(distinct work_date) filter (
                where extract(isodow from work_date) = 6
            ) as szombat,
            count(distinct work_date) filter (
                where extract(isodow from work_date) = 7
            ) as vasarnap,
            count(distinct work_date) filter (
                where extract(isodow from work_date) in (1,4,5,6)
            ) as kiemelt_napok,
            count(distinct work_date) filter (
                where extract(isodow from work_date) in (2,3,7)
            ) as sima_napok,
            count(distinct route_id) as kor_db,
            count(order_id) as cim_db,
            count(order_id) filter (
                where idoablakhoz_kepest_statusz = 'Késő'
            ) as keso_rendeles_db,
            count(order_id) filter (
                where idoablakhoz_kepest_statusz = 'Korai'
            ) as korai_rendeles_db,
            count(order_id) filter (
                where idoablakhoz_kepest_statusz in ('Korai', 'Késő')
            ) as nem_idoben_rendeles_db
        from public.dsp_order_arrivals
        group by date_trunc('month', work_date)::date, driver_id
    ),
    calc as (
        select
            *,
            round(kor_db::numeric / nullif(ledolgozott_napok, 0), 2)
                as kor_atlag_naponta,
            round(cim_db::numeric / nullif(kor_db, 0), 2)
                as cim_atlag_koronkent,
            round(cim_db::numeric / nullif(ledolgozott_napok, 0), 2)
                as cim_atlag_naponta,
            round(keso_rendeles_db::numeric / nullif(cim_db, 0) * 100, 2)
                as keses_szazalek,
            round(korai_rendeles_db::numeric / nullif(cim_db, 0) * 100, 2)
                as korai_szazalek,
            round(nem_idoben_rendeles_db::numeric / nullif(cim_db, 0) * 100, 2)
                as nem_idoben_szazalek
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
        end,
        case
            when keses_szazalek <= 1.5 then 3000
            when keses_szazalek <= 3 then 1000
            when keses_szazalek <= 5 then 500
            else 0
        end,
        case
            when nem_idoben_szazalek <= 1.5 then 'Megfelelési-1'
            when nem_idoben_szazalek <= 4 then 'Megfelelési-2'
            when nem_idoben_szazalek <= 10 then 'Megfelelési-3'
            else 'Nincs megfelelési bónusz'
        end,
        case
            when nem_idoben_szazalek <= 1.5 then 3000
            when nem_idoben_szazalek <= 4 then 1000
            when nem_idoben_szazalek <= 10 then 500
            else 0
        end,
        kiemelt_napok * 13000,
        sima_napok * 11000,
        (kiemelt_napok * 13000) + (sima_napok * 11000),
        now()
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
    """
)


UPSERT_COMPANY_KPI_SQL = dedent(
    """
    insert into public.dsp_company_kpi_summary (
        work_month,
        total_orders,
        total_routes,
        total_drivers,
        worked_days,
        idoben_db,
        idoben_szazalek,
        korai_db,
        korai_szazalek,
        keso_db,
        keso_szazalek,
        idokapun_kivuli_db,
        idokapun_kivuli_szazalek,
        rendeles_atlag_koronkent,
        kor_atlag_naponta,
        rendeles_atlag_naponta,
        updated_at
    )
    with summary as (
        select
            date_trunc('month', work_date)::date as work_month,
            count(order_id) as total_orders,
            count(distinct (work_date, driver_id, route_id)) as total_routes,
            count(distinct driver_id) as total_drivers,
            count(distinct work_date) as worked_days,
            count(order_id) filter (
                where idoablakhoz_kepest_statusz = 'Időben'
            ) as idoben_db,
            count(order_id) filter (
                where idoablakhoz_kepest_statusz = 'Korai'
            ) as korai_db,
            count(order_id) filter (
                where idoablakhoz_kepest_statusz = 'Késő'
            ) as keso_db,
            count(order_id) filter (
                where idoablakhoz_kepest_statusz in ('Korai', 'Késő')
            ) as idokapun_kivuli_db
        from public.dsp_order_arrivals
        group by date_trunc('month', work_date)::date
    )
    select
        work_month,
        total_orders,
        total_routes,
        total_drivers,
        worked_days,
        idoben_db,
        round(idoben_db::numeric / nullif(total_orders, 0) * 100, 2),
        korai_db,
        round(korai_db::numeric / nullif(total_orders, 0) * 100, 2),
        keso_db,
        round(keso_db::numeric / nullif(total_orders, 0) * 100, 2),
        idokapun_kivuli_db,
        round(idokapun_kivuli_db::numeric / nullif(total_orders, 0) * 100, 2),
        round(total_orders::numeric / nullif(total_routes, 0), 2),
        round(total_routes::numeric / nullif(worked_days, 0), 2),
        round(total_orders::numeric / nullif(worked_days, 0), 2),
        now()
    from summary
    on conflict (work_month)
    do update set
        total_orders = excluded.total_orders,
        total_routes = excluded.total_routes,
        total_drivers = excluded.total_drivers,
        worked_days = excluded.worked_days,
        idoben_db = excluded.idoben_db,
        idoben_szazalek = excluded.idoben_szazalek,
        korai_db = excluded.korai_db,
        korai_szazalek = excluded.korai_szazalek,
        keso_db = excluded.keso_db,
        keso_szazalek = excluded.keso_szazalek,
        idokapun_kivuli_db = excluded.idokapun_kivuli_db,
        idokapun_kivuli_szazalek = excluded.idokapun_kivuli_szazalek,
        rendeles_atlag_koronkent = excluded.rendeles_atlag_koronkent,
        kor_atlag_naponta = excluded.kor_atlag_naponta,
        rendeles_atlag_naponta = excluded.rendeles_atlag_naponta,
        updated_at = now();
    """
)


UPSERT_ATTENDANCE_COURIERS_SQL = dedent(
    """
    insert into public.dsp_attendance_couriers (
        work_date,
        dsp_id,
        dsp_name,
        courier_id,
        courier_name,
        warehouse_name,
        shift_count,
        route_count,
        updated_at
    )
    select
        coalesce(
            nullif(r.response_json ->> 'date', '')::date,
            r.work_date
        ) as work_date,
        r.response_json ->> 'dspId',
        r.response_json ->> 'dspName',
        nullif(courier.value ->> 'courierId', '')::integer,
        courier.value ->> 'courierName',
        courier.value ->> 'warehouseName',
        jsonb_array_length(
            coalesce(courier.value -> 'shifts', '[]'::jsonb)
        ),
        jsonb_array_length(
            coalesce(courier.value -> 'routes', '[]'::jsonb)
        ),
        now()
    from public.dsp_attendance_raw r
    cross join lateral jsonb_array_elements(
        coalesce(r.response_json -> 'couriers', '[]'::jsonb)
    ) courier(value)
    where nullif(courier.value ->> 'courierId', '') is not null
    on conflict (work_date, courier_id)
    do update set
        dsp_id = excluded.dsp_id,
        dsp_name = excluded.dsp_name,
        courier_name = excluded.courier_name,
        warehouse_name = excluded.warehouse_name,
        shift_count = excluded.shift_count,
        route_count = excluded.route_count,
        updated_at = now();
    """
)


UPSERT_ATTENDANCE_SHIFTS_SQL = dedent(
    """
    insert into public.dsp_attendance_shifts (
        work_date,
        dsp_id,
        dsp_name,
        courier_id,
        courier_name,
        warehouse_name,
        shift_id,
        shift_name,
        shift_start,
        shift_end,
        available_for_shift_since,
        available_diff_minutes,
        availability_status,
        updated_at
    )
    with extracted as (
        select
            coalesce(
                nullif(r.response_json ->> 'date', '')::date,
                r.work_date
            ) as work_date,
            r.response_json ->> 'dspId' as dsp_id,
            r.response_json ->> 'dspName' as dsp_name,
            nullif(courier.value ->> 'courierId', '')::integer as courier_id,
            courier.value ->> 'courierName' as courier_name,
            courier.value ->> 'warehouseName' as warehouse_name,
            shift_item.value as shift_json
        from public.dsp_attendance_raw r
        cross join lateral jsonb_array_elements(
            coalesce(r.response_json -> 'couriers', '[]'::jsonb)
        ) courier(value)
        cross join lateral jsonb_array_elements(
            coalesce(courier.value -> 'shifts', '[]'::jsonb)
        ) shift_item(value)
    )
    select
        work_date,
        dsp_id,
        dsp_name,
        courier_id,
        courier_name,
        warehouse_name,
        nullif(shift_json ->> 'shiftId', '')::bigint,
        shift_json ->> 'shiftName',
        (
            nullif(shift_json ->> 'shiftStart', '')::timestamptz
            at time zone 'Europe/Budapest'
        )::timestamp,
        (
            nullif(shift_json ->> 'shiftEnd', '')::timestamptz
            at time zone 'Europe/Budapest'
        )::timestamp,
        (
            nullif(shift_json ->> 'availableForShiftSince', '')::timestamptz
            at time zone 'Europe/Budapest'
        )::timestamp,
        round(
            extract(
                epoch from (
                    nullif(shift_json ->> 'availableForShiftSince', '')::timestamptz
                    - nullif(shift_json ->> 'shiftStart', '')::timestamptz
                )
            ) / 60
        )::integer,
        case
            when nullif(shift_json ->> 'availableForShiftSince', '') is null
                then 'Nem jelentkezett elérhetőnek'
            when nullif(shift_json ->> 'shiftStart', '') is null
                then 'Nincs műszakkezdés'
            when
                nullif(shift_json ->> 'availableForShiftSince', '')::timestamptz
                <= nullif(shift_json ->> 'shiftStart', '')::timestamptz
                then 'Időben elérhető'
            else 'Későn elérhető'
        end,
        now()
    from extracted
    where courier_id is not null
      and nullif(shift_json ->> 'shiftId', '') is not null
    on conflict (work_date, courier_id, shift_id)
    do update set
        dsp_id = excluded.dsp_id,
        dsp_name = excluded.dsp_name,
        courier_name = excluded.courier_name,
        warehouse_name = excluded.warehouse_name,
        shift_name = excluded.shift_name,
        shift_start = excluded.shift_start,
        shift_end = excluded.shift_end,
        available_for_shift_since = excluded.available_for_shift_since,
        available_diff_minutes = excluded.available_diff_minutes,
        availability_status = excluded.availability_status,
        updated_at = now();
    """
)


UPSERT_ATTENDANCE_ROUTES_SQL = dedent(
    """
    insert into public.dsp_attendance_routes (
        work_date,
        dsp_id,
        dsp_name,
        courier_id,
        courier_name,
        warehouse_name,
        route_id,
        courier_registered_at,
        assigned_at,
        planned_departure,
        real_departure,
        planned_return,
        real_return,
        planned_route_minutes,
        real_route_minutes,
        departure_diff_minutes,
        return_diff_minutes,
        departure_status,
        return_status,
        updated_at
    )
    with extracted as (
        select
            coalesce(
                nullif(r.response_json ->> 'date', '')::date,
                r.work_date
            ) as work_date,
            r.response_json ->> 'dspId' as dsp_id,
            r.response_json ->> 'dspName' as dsp_name,
            nullif(courier.value ->> 'courierId', '')::integer as courier_id,
            courier.value ->> 'courierName' as courier_name,
            courier.value ->> 'warehouseName' as warehouse_name,
            route_item.value as route_json
        from public.dsp_attendance_raw r
        cross join lateral jsonb_array_elements(
            coalesce(r.response_json -> 'couriers', '[]'::jsonb)
        ) courier(value)
        cross join lateral jsonb_array_elements(
            coalesce(courier.value -> 'routes', '[]'::jsonb)
        ) route_item(value)
    ),
    parsed as (
        select
            *,
            nullif(route_json ->> 'routeId', '')::bigint as route_id,
            nullif(route_json ->> 'courierRegisteredAt', '')::timestamptz
                as registered_utc,
            nullif(route_json ->> 'assignedAt', '')::timestamptz
                as assigned_utc,
            nullif(route_json ->> 'plannedDeparture', '')::timestamptz
                as planned_departure_utc,
            nullif(route_json ->> 'realDeparture', '')::timestamptz
                as real_departure_utc,
            nullif(route_json ->> 'plannedReturn', '')::timestamptz
                as planned_return_utc,
            nullif(route_json ->> 'realReturn', '')::timestamptz
                as real_return_utc
        from extracted
    )
    select
        work_date,
        dsp_id,
        dsp_name,
        courier_id,
        courier_name,
        warehouse_name,
        route_id,
        (registered_utc at time zone 'Europe/Budapest')::timestamp,
        (assigned_utc at time zone 'Europe/Budapest')::timestamp,
        (planned_departure_utc at time zone 'Europe/Budapest')::timestamp,
        (real_departure_utc at time zone 'Europe/Budapest')::timestamp,
        (planned_return_utc at time zone 'Europe/Budapest')::timestamp,
        (real_return_utc at time zone 'Europe/Budapest')::timestamp,
        round(
            extract(epoch from (planned_return_utc - planned_departure_utc)) / 60
        )::integer,
        round(
            extract(epoch from (real_return_utc - real_departure_utc)) / 60
        )::integer,
        round(
            extract(epoch from (real_departure_utc - planned_departure_utc)) / 60
        )::integer,
        round(
            extract(epoch from (real_return_utc - planned_return_utc)) / 60
        )::integer,
        case
            when real_departure_utc is null then 'Nincs valós indulás'
            when planned_departure_utc is null then 'Nincs tervezett indulás'
            when real_departure_utc <= planned_departure_utc then 'Időben indult'
            else 'Későn indult'
        end,
        case
            when real_return_utc is null then 'Nincs valós visszaérkezés'
            when planned_return_utc is null then 'Nincs tervezett visszaérkezés'
            when real_return_utc <= planned_return_utc then 'Időben visszaért'
            else 'Későn ért vissza'
        end,
        now()
    from parsed
    where courier_id is not null
      and route_id is not null
    on conflict (work_date, courier_id, route_id)
    do update set
        dsp_id = excluded.dsp_id,
        dsp_name = excluded.dsp_name,
        courier_name = excluded.courier_name,
        warehouse_name = excluded.warehouse_name,
        courier_registered_at = excluded.courier_registered_at,
        assigned_at = excluded.assigned_at,
        planned_departure = excluded.planned_departure,
        real_departure = excluded.real_departure,
        planned_return = excluded.planned_return,
        real_return = excluded.real_return,
        planned_route_minutes = excluded.planned_route_minutes,
        real_route_minutes = excluded.real_route_minutes,
        departure_diff_minutes = excluded.departure_diff_minutes,
        return_diff_minutes = excluded.return_diff_minutes,
        departure_status = excluded.departure_status,
        return_status = excluded.return_status,
        updated_at = now();
    """
)


UPSERT_SHIFT_ROUTE_SUMMARY_SQL = dedent(
    """
    insert into public.dsp_shift_route_summary (
        work_date,
        courier_id,
        courier_name,
        warehouse_name,
        shift_id,
        shift_name,
        shift_start,
        shift_end,
        available_for_shift_since,
        route_id,
        courier_registered_at,
        assigned_at,
        planned_departure,
        planned_return,
        planned_route_minutes,
        real_departure,
        real_return,
        real_route_minutes,
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
    select
        r.work_date,
        r.courier_id,
        r.courier_name,
        r.warehouse_name,
        s.shift_id,
        s.shift_name,
        s.shift_start,
        s.shift_end,
        s.available_for_shift_since,
        r.route_id,
        r.courier_registered_at,
        r.assigned_at,
        r.planned_departure,
        r.planned_return,
        r.planned_route_minutes,
        r.real_departure,
        r.real_return,
        r.real_route_minutes,
        d.orders,
        d.keso_rendelesek,
        d.korai_rendelesek,
        d.nem_idoben_rendelesek,
        d.keses_szazalek,
        d.korai_szazalek,
        d.nem_idoben_szazalek,
        d.kesedelmi_kategoria,
        d.megfelelesi_kategoria,
        d.city_delay_bonus,
        d.city_compliance_bonus,
        now()
    from public.dsp_attendance_routes r
    left join lateral (
        select shift_row.*
        from public.dsp_attendance_shifts shift_row
        where shift_row.work_date = r.work_date
          and shift_row.courier_id = r.courier_id
          and (
              (
                  r.planned_departure is not null
                  and r.planned_departure between shift_row.shift_start and shift_row.shift_end
              )
              or (
                  r.courier_registered_at is not null
                  and r.courier_registered_at between shift_row.shift_start and shift_row.shift_end
              )
          )
        order by
            case
                when r.planned_departure is null or shift_row.shift_start is null
                    then interval '999 days'
                else abs(r.planned_departure - shift_row.shift_start)
            end
        limit 1
    ) s on true
    left join public.dsp_route_delay_statistics d
      on d.work_date = r.work_date
     and d.driver_id = r.courier_id
     and d.route_id = r.route_id::text
    on conflict (work_date, courier_id, route_id)
    do update set
        courier_name = excluded.courier_name,
        warehouse_name = excluded.warehouse_name,
        shift_id = excluded.shift_id,
        shift_name = excluded.shift_name,
        shift_start = excluded.shift_start,
        shift_end = excluded.shift_end,
        available_for_shift_since = excluded.available_for_shift_since,
        courier_registered_at = excluded.courier_registered_at,
        assigned_at = excluded.assigned_at,
        planned_departure = excluded.planned_departure,
        planned_return = excluded.planned_return,
        planned_route_minutes = excluded.planned_route_minutes,
        real_departure = excluded.real_departure,
        real_return = excluded.real_return,
        real_route_minutes = excluded.real_route_minutes,
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
    """
)


CHECK_SQL = dedent(
    """
    select 'dsp_driver_detail_raw' as tabla, count(*) as sorok
    from public.dsp_driver_detail_raw

    union all
    select 'dsp_attendance_raw', count(*)
    from public.dsp_attendance_raw

    union all
    select 'dsp_order_arrivals', count(*)
    from public.dsp_order_arrivals

    union all
    select 'dsp_route_delay_statistics', count(*)
    from public.dsp_route_delay_statistics

    union all
    select 'dsp_driver_month_summary', count(*)
    from public.dsp_driver_month_summary

    union all
    select 'dsp_company_kpi_summary', count(*)
    from public.dsp_company_kpi_summary

    union all
    select 'dsp_attendance_couriers', count(*)
    from public.dsp_attendance_couriers

    union all
    select 'dsp_attendance_shifts', count(*)
    from public.dsp_attendance_shifts

    union all
    select 'dsp_attendance_routes', count(*)
    from public.dsp_attendance_routes

    union all
    select 'dsp_shift_route_summary', count(*)
    from public.dsp_shift_route_summary

    order by tabla;
    """
)


PIPELINE = [
    ("Táblák létrehozása és bővítése", CREATE_TABLES_SQL),
    ("Rendelési érkezések", UPSERT_ORDER_ARRIVALS_SQL),
    ("Route késési statisztika", UPSERT_ROUTE_DELAY_SQL),
    ("Futár havi összesítő", UPSERT_DRIVER_MONTH_SQL),
    ("Céges KPI összesítő", UPSERT_COMPANY_KPI_SQL),
    ("Attendance futárok", UPSERT_ATTENDANCE_COURIERS_SQL),
    ("Attendance műszakok", UPSERT_ATTENDANCE_SHIFTS_SQL),
    ("Attendance túrák", UPSERT_ATTENDANCE_ROUTES_SQL),
    ("Műszak + túra + késési statisztika", UPSERT_SHIFT_ROUTE_SUMMARY_SQL),
]


def run_sql(cursor, step_number: int, total_steps: int, name: str, sql: str) -> None:
    print(f"\n[{step_number}/{total_steps}] Fut: {name}")
    cursor.execute(sql)
    print(f"[{step_number}/{total_steps}] Kész: {name}")


def main() -> None:
    print("DSP összesítő pipeline indul.")
    print("A RAW és a cél táblákból sem törlünk adatot.")

    try:
        database_url = get_database_url()

        with psycopg2.connect(database_url) as connection:
            with connection.cursor() as cursor:
                configuration_sql = read_configuration_sql()
                total_steps = len(PIPELINE) + (1 if configuration_sql else 0)
                step_number = 1

                if configuration_sql:
                    run_sql(
                        cursor=cursor,
                        step_number=step_number,
                        total_steps=total_steps,
                        name="DSP konfiguracios tablak es seed adatok",
                        sql=configuration_sql,
                    )
                    step_number += 1

                for name, sql in PIPELINE:
                    run_sql(
                        cursor=cursor,
                        step_number=step_number,
                        total_steps=total_steps,
                        name=name,
                        sql=sql,
                    )
                    step_number += 1

                connection.commit()

                cursor.execute(CHECK_SQL)
                rows = cursor.fetchall()

        print("\nEllenőrzés:")
        for table_name, row_count in rows:
            print(f"- {table_name}: {row_count} sor")

        print("\nDSP összesítő pipeline sikeresen lefutott.")

    except Exception as exc:
        print(f"\nHIBA: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
