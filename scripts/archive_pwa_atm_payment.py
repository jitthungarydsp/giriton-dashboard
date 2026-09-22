from __future__ import annotations

import argparse
import base64
import csv
import json
import mimetypes
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

try:
    from resources.supabase_raw import get_supabase_config, raise_for_supabase_error
except ModuleNotFoundError:
    import sys

    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


TABLE_NAME = "pwa_atm_payment"
CONFIRM_DELETE = "ARCHIVE_PWA_ATM_PAYMENT"
EXPORT_COLUMNS = (
    "id,courier_id,courier_name,amount_huf,invoice_number,note,file_name,"
    "mime_type,file_size,file_content_base64,status,paid_at,created_by,created_at,updated_at"
)


def clean_filename(value: Any, default: str = "file") -> str:
    text = str(value or "").strip() or default
    text = re.sub(r"[^\w.\-]+", "_", text, flags=re.ASCII)
    return text.strip("._") or default


def extension_for(mime_type: str, file_name: str) -> str:
    suffix = Path(file_name or "").suffix
    if suffix:
        return suffix
    guessed = mimetypes.guess_extension(mime_type or "")
    return guessed or ".bin"


def supabase_headers(service_role_key: str, *, prefer: str = "") -> dict[str, str]:
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def fetch_rows(
    supabase_url: str,
    service_role_key: str,
    *,
    date_column: str,
    cutoff_date: str,
    page_size: int,
    max_rows: int | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = max(1, min(int(page_size), 1000))

    while True:
        if max_rows is not None and len(rows) >= max_rows:
            break

        limit = page_size
        if max_rows is not None:
            limit = min(limit, max_rows - len(rows))

        params = {
            "select": EXPORT_COLUMNS,
            date_column: f"lt.{cutoff_date}",
            "order": f"{date_column}.asc",
            "limit": str(limit),
            "offset": str(offset),
        }
        response = requests.get(
            f"{supabase_url}/rest/v1/{TABLE_NAME}",
            headers=supabase_headers(service_role_key),
            params=params,
            timeout=90,
        )
        raise_for_supabase_error(response)
        chunk = response.json()

        if not chunk:
            break

        rows.extend(chunk)
        offset += len(chunk)

        if len(chunk) < limit:
            break

    return rows


def write_archive(rows: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = out_dir / f"{TABLE_NAME}_{stamp}"
    receipts_dir = archive_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    metadata_jsonl = archive_dir / "metadata.jsonl"
    metadata_csv = archive_dir / "metadata.csv"

    exported_rows: list[dict[str, Any]] = []
    receipt_count = 0
    receipt_bytes = 0

    with metadata_jsonl.open("w", encoding="utf-8") as jsonl_file:
        for index, row in enumerate(rows, start=1):
            exported = dict(row)
            content_base64 = str(exported.pop("file_content_base64", "") or "").strip()
            receipt_path = ""
            receipt_error = ""

            if content_base64:
                try:
                    content = base64.b64decode(content_base64, validate=True)
                    row_id = clean_filename(row.get("id"), default=f"row_{index}")
                    original_name = clean_filename(row.get("file_name"), default="receipt")
                    ext = extension_for(str(row.get("mime_type") or ""), original_name)
                    receipt_name = f"{row_id}_{original_name}"
                    if not Path(receipt_name).suffix:
                        receipt_name += ext
                    receipt_file = receipts_dir / receipt_name
                    receipt_file.write_bytes(content)
                    receipt_path = str(receipt_file.relative_to(archive_dir)).replace("\\", "/")
                    receipt_count += 1
                    receipt_bytes += len(content)
                except Exception as exc:  # noqa: BLE001 - keep exporting metadata even if one receipt is bad.
                    receipt_error = str(exc)

            exported["receipt_archive_path"] = receipt_path
            exported["receipt_archive_error"] = receipt_error
            exported_rows.append(exported)
            jsonl_file.write(json.dumps(exported, ensure_ascii=False, default=str) + "\n")

    csv_columns = [
        "id",
        "courier_id",
        "courier_name",
        "amount_huf",
        "invoice_number",
        "note",
        "file_name",
        "mime_type",
        "file_size",
        "status",
        "paid_at",
        "created_by",
        "created_at",
        "updated_at",
        "receipt_archive_path",
        "receipt_archive_error",
    ]
    with metadata_csv.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=csv_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(exported_rows)

    return {
        "archive_dir": archive_dir,
        "metadata_jsonl": metadata_jsonl,
        "metadata_csv": metadata_csv,
        "rows": len(exported_rows),
        "receipts": receipt_count,
        "receipt_bytes": receipt_bytes,
    }


def zip_archive(archive_dir: Path) -> Path:
    zip_path = archive_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for path in archive_dir.rglob("*"):
            if path.is_file():
                zip_file.write(path, path.relative_to(archive_dir.parent))
    return zip_path


def delete_rows(
    supabase_url: str,
    service_role_key: str,
    *,
    date_column: str,
    cutoff_date: str,
) -> None:
    params = {
        date_column: f"lt.{cutoff_date}",
    }
    response = requests.delete(
        f"{supabase_url}/rest/v1/{TABLE_NAME}",
        headers=supabase_headers(service_role_key, prefer="return=minimal"),
        params=params,
        timeout=120,
    )
    raise_for_supabase_error(response)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="pwa_atm_payment bizonylatok archiválása Supabase-ből."
    )
    parser.add_argument("--cutoff-date", required=True, help="Eddig a dátumig archivál: pl. 2026-08-01")
    parser.add_argument("--date-column", default="created_at", help="Dátum mező: created_at vagy paid_at")
    parser.add_argument("--out-dir", default="archive/pwa_atm_payment", help="Archívum célmappa")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--max-rows", type=int, default=0, help="Teszt limit. 0 = nincs limit")
    parser.add_argument("--no-zip", action="store_true", help="Ne készítsen ZIP-et")
    parser.add_argument(
        "--allow-current-month",
        action="store_true",
        help="Védőkorlát feloldása: engedi az aktuális hónap érintését.",
    )
    parser.add_argument("--delete", action="store_true", help="Sikeres mentés után törölje is a DB-ből")
    parser.add_argument(
        "--confirm-delete",
        default="",
        help=f"Törléshez pontosan ezt add meg: {CONFIRM_DELETE}",
    )
    return parser.parse_args()


def validate_cutoff_date(cutoff_date: str, *, allow_current_month: bool) -> None:
    try:
        cutoff = date.fromisoformat(cutoff_date)
    except ValueError as exc:
        raise RuntimeError("A --cutoff-date formátuma legyen YYYY-MM-DD, például 2026-08-01.") from exc

    today = date.today()
    current_month_start = today.replace(day=1)

    if cutoff >= current_month_start and not allow_current_month:
        raise RuntimeError(
            "Az aktuális hónapot alapból nem archiválom/törlöm. "
            f"Adj meg korábbi cutoff dátumot, például {current_month_start.isoformat()} előtti napot. "
            "Ha ezt tényleg felül akarod írni, használd az --allow-current-month kapcsolót."
        )


def main() -> int:
    args = parse_args()
    validate_cutoff_date(args.cutoff_date, allow_current_month=args.allow_current_month)
    supabase_url, service_role_key = get_supabase_config()
    if not supabase_url or not service_role_key:
        raise RuntimeError("Hiányzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY beállítás.")

    max_rows = int(args.max_rows) if int(args.max_rows or 0) > 0 else None
    out_dir = Path(args.out_dir)
    rows = fetch_rows(
        supabase_url,
        service_role_key,
        date_column=args.date_column,
        cutoff_date=args.cutoff_date,
        page_size=args.page_size,
        max_rows=max_rows,
    )

    if not rows:
        print("Nincs archiválandó sor.")
        return 0

    summary = write_archive(rows, out_dir)
    zip_path = None if args.no_zip else zip_archive(summary["archive_dir"])

    print(f"Archivált sorok: {summary['rows']}")
    print(f"Kimentett bizonylatok: {summary['receipts']}")
    print(f"Bizonylatok mérete: {summary['receipt_bytes']} byte")
    print(f"Archív mappa: {summary['archive_dir']}")
    if zip_path:
        print(f"ZIP: {zip_path}")

    if args.delete:
        if args.confirm_delete != CONFIRM_DELETE:
            raise RuntimeError(
                f"A törléshez add meg: --confirm-delete {CONFIRM_DELETE}"
            )
        if summary["rows"] <= 0:
            raise RuntimeError("Nem törlök, mert nem készült sikeres export.")
        delete_rows(
            supabase_url,
            service_role_key,
            date_column=args.date_column,
            cutoff_date=args.cutoff_date,
        )
        print("DB törlés kész.")
    else:
        print("DB törlés kihagyva. Törléshez külön futtasd --delete kapcsolóval.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
