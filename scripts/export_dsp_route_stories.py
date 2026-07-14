#!/usr/bin/env python3
"""
mart_dsp_route_stories exportálása Excel fájlba.

Használat:
    python scripts/export_dsp_route_stories.py
    python scripts/export_dsp_route_stories.py --start-date 2026-06-01
    python scripts/export_dsp_route_stories.py --start-date 2026-06-01 --end-date 2026-07-11
    python scripts/export_dsp_route_stories.py --courier-id 7056
    python scripts/export_dsp_route_stories.py --output exports/route_stories.xlsx

Szükséges környezeti változók:
    SUPABASE_URL
    SUPABASE_KEY

Telepítés:
    pip install requests xlsxwriter
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
import xlsxwriter


TABLE_NAME = "mart_dsp_route_stories"
PAGE_SIZE = 500

COLUMNS = [
    "work_date",
    "courier_id",
    "courier_name",
    "warehouse_name",
    "route_id",
    "shift_id",
    "shift_name",
    "shift_start",
    "shift_end",
    "available_for_shift_since",
    "courier_registered_at",
    "assigned_at",
    "planned_departure",
    "real_departure",
    "planned_return",
    "real_return",
    "queue_entry_delta_minutes",
    "queue_wait_minutes",
    "planned_loading_minutes",
    "real_loading_minutes",
    "planned_route_minutes",
    "real_route_minutes",
    "assigned_to_return_minutes",
    "address_count",
    "planned_early_count",
    "planned_late_count",
    "time_window_early_count",
    "time_window_late_count",
    "assignment_mode",
    "story_text",
    "source_summary_table",
    "source_arrivals_table",
    "created_at",
    "updated_at",
]

HEADERS_HU = {
    "work_date": "Dátum",
    "courier_id": "Futár ID",
    "courier_name": "Futár neve",
    "warehouse_name": "Raktár",
    "route_id": "Túra ID",
    "shift_id": "Műszak ID",
    "shift_name": "Műszak neve",
    "shift_start": "Műszak kezdete",
    "shift_end": "Műszak vége",
    "available_for_shift_since": "Elérhető ettől",
    "courier_registered_at": "Regisztrált",
    "assigned_at": "Túrára rakva",
    "planned_departure": "Tervezett indulás",
    "real_departure": "Valós indulás",
    "planned_return": "Tervezett visszaérkezés",
    "real_return": "Valós visszaérkezés",
    "queue_entry_delta_minutes": "Sorba állás eltérés (perc)",
    "queue_wait_minutes": "Sorban várakozás (perc)",
    "planned_loading_minutes": "Tervezett rakodás (perc)",
    "real_loading_minutes": "Valós rakodás (perc)",
    "planned_route_minutes": "Tervezett túraidő (perc)",
    "real_route_minutes": "Valós túraidő (perc)",
    "assigned_to_return_minutes": "Kiosztástól visszaérkezésig (perc)",
    "address_count": "Címek száma",
    "planned_early_count": "Tervezetthez korai",
    "planned_late_count": "Tervezetthez késő",
    "time_window_early_count": "Időablakhoz korai",
    "time_window_late_count": "Időablakhoz késő",
    "assignment_mode": "Kiosztás módja",
    "story_text": "Túra története",
    "source_summary_table": "Forrás összesítő",
    "source_arrivals_table": "Forrás érkezések",
    "created_at": "Létrehozva",
    "updated_at": "Frissítve",
}

DATE_COLUMNS = {"work_date"}
DATETIME_COLUMNS = {
    "shift_start",
    "shift_end",
    "available_for_shift_since",
    "courier_registered_at",
    "assigned_at",
    "planned_departure",
    "real_departure",
    "planned_return",
    "real_return",
    "created_at",
    "updated_at",
}
INTEGER_COLUMNS = {
    "courier_id",
    "route_id",
    "shift_id",
    "queue_entry_delta_minutes",
    "queue_wait_minutes",
    "planned_loading_minutes",
    "real_loading_minutes",
    "planned_route_minutes",
    "real_route_minutes",
    "assigned_to_return_minutes",
    "address_count",
    "planned_early_count",
    "planned_late_count",
    "time_window_early_count",
    "time_window_late_count",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="mart_dsp_route_stories exportálása Excelbe"
    )
    parser.add_argument("--start-date", help="Kezdő dátum, például 2026-06-01")
    parser.add_argument("--end-date", help="Záró dátum, például 2026-07-11")
    parser.add_argument("--courier-id", type=int, help="Csak egy futár exportálása")
    parser.add_argument(
        "--output",
        help="Kimeneti Excel fájl",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=PAGE_SIZE,
        help=f"Supabase lapméret, alapértelmezés: {PAGE_SIZE}",
    )
    return parser.parse_args()


def validate_iso_date(value: str | None, field_name: str) -> None:
    if not value:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Hibás {field_name}: {value!r}. Elvárt formátum: ÉÉÉÉ-HH-NN."
        ) from exc


def get_supabase_settings() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )

    if not url:
        raise RuntimeError("Hiányzik a SUPABASE_URL környezeti változó.")
    if not key:
        raise RuntimeError(
            "Hiányzik a SUPABASE_KEY vagy SUPABASE_SERVICE_ROLE_KEY "
            "környezeti változó."
        )

    return url, key


def raise_for_supabase_error(
    response: requests.Response,
    *,
    table_name: str,
) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        try:
            details: Any = response.json()
        except ValueError:
            details = response.text

        raise requests.HTTPError(
            f"Supabase hiba: HTTP {response.status_code}; "
            f"tábla={table_name}; url={response.url}; válasz={details}"
        ) from exc


def fetch_rows(
    *,
    supabase_url: str,
    supabase_key: str,
    start_date: str | None,
    end_date: str | None,
    courier_id: int | None,
    page_size: int,
) -> list[dict[str, Any]]:
    if page_size < 1 or page_size > 1000:
        raise ValueError("--page-size értéke 1 és 1000 között legyen.")

    endpoint = f"{supabase_url}/rest/v1/{TABLE_NAME}"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Accept": "application/json",
    }

    all_rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        params: list[tuple[str, str]] = [
            ("select", ",".join(COLUMNS)),
            ("order", "work_date.asc,courier_id.asc,route_id.asc"),
            ("limit", str(page_size)),
            ("offset", str(offset)),
        ]

        if start_date:
            params.append(("work_date", f"gte.{start_date}"))
        if end_date:
            params.append(("work_date", f"lte.{end_date}"))
        if courier_id is not None:
            params.append(("courier_id", f"eq.{courier_id}"))

        response = requests.get(
            endpoint,
            headers=headers,
            params=params,
            timeout=120,
        )
        raise_for_supabase_error(response, table_name=TABLE_NAME)

        page = response.json()
        if not isinstance(page, list):
            raise RuntimeError(f"Váratlan Supabase válasz: {page!r}")

        all_rows.extend(page)
        print(
            f"Letöltve: {len(page):>4} sor | "
            f"összesen: {len(all_rows):>6} sor"
        )

        if len(page) < page_size:
            break

        offset += page_size

    return all_rows


def parse_date_value(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def parse_datetime_value(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        normalized = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)

    # Excel nem kezeli az időzóna-információt.
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)

    return dt


def default_output_name(
    start_date: str | None,
    end_date: str | None,
    courier_id: int | None,
) -> Path:
    parts = ["mart_dsp_route_stories"]
    if start_date:
        parts.append(start_date)
    if end_date:
        parts.append(end_date)
    if courier_id is not None:
        parts.append(f"courier_{courier_id}")

    return Path("exports") / ("_".join(parts) + ".xlsx")


def write_excel(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = xlsxwriter.Workbook(
        str(output_path),
        {
            "constant_memory": True,
            "in_memory": False,
        },
    )
    worksheet = workbook.add_worksheet("Route stories")

    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#1F4E78",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
        }
    )
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd"})
    datetime_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})
    integer_format = workbook.add_format({"num_format": "0"})
    text_format = workbook.add_format({"valign": "top"})
    story_format = workbook.add_format({"valign": "top", "text_wrap": True})

    for col_idx, column in enumerate(COLUMNS):
        worksheet.write(0, col_idx, HEADERS_HU.get(column, column), header_format)

    for row_idx, row in enumerate(rows, start=1):
        for col_idx, column in enumerate(COLUMNS):
            value = row.get(column)

            try:
                if column in DATE_COLUMNS:
                    parsed = parse_date_value(value)
                    if parsed is None:
                        worksheet.write_blank(row_idx, col_idx, None)
                    else:
                        worksheet.write_datetime(
                            row_idx,
                            col_idx,
                            datetime.combine(parsed, datetime.min.time()),
                            date_format,
                        )
                elif column in DATETIME_COLUMNS:
                    parsed_dt = parse_datetime_value(value)
                    if parsed_dt is None:
                        worksheet.write_blank(row_idx, col_idx, None)
                    else:
                        worksheet.write_datetime(
                            row_idx,
                            col_idx,
                            parsed_dt,
                            datetime_format,
                        )
                elif column in INTEGER_COLUMNS:
                    if value in (None, ""):
                        worksheet.write_blank(row_idx, col_idx, None)
                    else:
                        worksheet.write_number(
                            row_idx,
                            col_idx,
                            int(value),
                            integer_format,
                        )
                elif column == "story_text":
                    worksheet.write(
                        row_idx,
                        col_idx,
                        "" if value is None else str(value),
                        story_format,
                    )
                else:
                    worksheet.write(
                        row_idx,
                        col_idx,
                        "" if value is None else str(value),
                        text_format,
                    )
            except (TypeError, ValueError) as exc:
                # Egy hibás mező miatt ne álljon le a teljes export.
                worksheet.write(
                    row_idx,
                    col_idx,
                    "" if value is None else str(value),
                    text_format,
                )
                print(
                    f"Figyelmeztetés: sor={row_idx + 1}, oszlop={column}, "
                    f"érték={value!r}, hiba={exc}",
                    file=sys.stderr,
                )

    last_row = max(len(rows), 1)
    last_col = len(COLUMNS) - 1

    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, last_row, last_col)
    worksheet.set_row(0, 34)

    widths = {
        "work_date": 12,
        "courier_id": 11,
        "courier_name": 24,
        "warehouse_name": 18,
        "route_id": 14,
        "shift_id": 14,
        "shift_name": 24,
        "shift_start": 20,
        "shift_end": 20,
        "available_for_shift_since": 20,
        "courier_registered_at": 20,
        "assigned_at": 20,
        "planned_departure": 20,
        "real_departure": 20,
        "planned_return": 20,
        "real_return": 20,
        "queue_entry_delta_minutes": 17,
        "queue_wait_minutes": 17,
        "planned_loading_minutes": 17,
        "real_loading_minutes": 17,
        "planned_route_minutes": 17,
        "real_route_minutes": 17,
        "assigned_to_return_minutes": 20,
        "address_count": 12,
        "planned_early_count": 15,
        "planned_late_count": 15,
        "time_window_early_count": 15,
        "time_window_late_count": 15,
        "assignment_mode": 18,
        "story_text": 70,
        "source_summary_table": 25,
        "source_arrivals_table": 25,
        "created_at": 20,
        "updated_at": 20,
    }

    for col_idx, column in enumerate(COLUMNS):
        worksheet.set_column(col_idx, col_idx, widths.get(column, 16))

    # Késések kiemelése.
    for column in (
        "planned_late_count",
        "time_window_late_count",
    ):
        col_idx = COLUMNS.index(column)
        worksheet.conditional_format(
            1,
            col_idx,
            last_row,
            col_idx,
            {
                "type": "cell",
                "criteria": ">",
                "value": 0,
                "format": workbook.add_format(
                    {"bg_color": "#FFC7CE", "font_color": "#9C0006"}
                ),
            },
        )

    workbook.close()


def main() -> int:
    args = parse_args()

    try:
        validate_iso_date(args.start_date, "--start-date")
        validate_iso_date(args.end_date, "--end-date")

        if (
            args.start_date
            and args.end_date
            and args.start_date > args.end_date
        ):
            raise ValueError(
                "A --start-date nem lehet későbbi, mint az --end-date."
            )

        supabase_url, supabase_key = get_supabase_settings()

        output_path = (
            Path(args.output)
            if args.output
            else default_output_name(
                args.start_date,
                args.end_date,
                args.courier_id,
            )
        )

        print(f"Forrás: public.{TABLE_NAME}")
        print(
            f"Szűrés: {args.start_date or '-∞'} - "
            f"{args.end_date or '+∞'}"
        )
        if args.courier_id is not None:
            print(f"Futár ID: {args.courier_id}")

        rows = fetch_rows(
            supabase_url=supabase_url,
            supabase_key=supabase_key,
            start_date=args.start_date,
            end_date=args.end_date,
            courier_id=args.courier_id,
            page_size=args.page_size,
        )

        write_excel(rows, output_path)

        print(f"\nKész: {output_path.resolve()}")
        print(f"Exportált sorok: {len(rows)}")
        return 0

    except KeyboardInterrupt:
        print("\nMegszakítva.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"\nHIBA: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
