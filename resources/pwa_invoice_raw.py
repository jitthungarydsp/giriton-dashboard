"""Phase 1 workbook archiving. No settlement processing or financial calculations."""
from datetime import date, datetime, time
from io import BytesIO
import hashlib
import json
import math
from pathlib import PureWindowsPath
from uuid import UUID, uuid4
from zipfile import ZipFile, BadZipFile

from openpyxl import load_workbook

TABLE = "PWA_INVOICE_RAW"
BUCKET = "pwa-attachments"
PREFIX = "pwa-invoice-raw"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_RAW_BYTES = 25 * 1024 * 1024
MAX_VISITED_CELLS = 2_000_000
METADATA_FIELDS = "id,session_id,settlement_month,source_file_name,file_sha256,file_size_bytes,sheet_count,raw_row_count,status,created_by,created_at"


class RawImportError(Exception):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def database_error(exc):
    text = str(exc)
    if any(code in text for code in ("PGRST205", "PGRST202", "42P01", "42883")):
        return RawImportError("Az új RAW tároló még nincs telepítve. Futtasd a sql/pwa_invoice_raw_phase1.sql fájlt a Supabase SQL Editorban.", 503)
    return RawImportError("A RAW mentés jelenleg nem igazolható. Ugyanazon fájl újrapróbálása ugyanazzal a kérésazonosítóval történik.", 502)


def month_start(value):
    try:
        parsed = date.fromisoformat(str(value) + "-01")
    except ValueError as exc:
        raise RawImportError("Érvénytelen elszámolási hónap.") from exc
    return parsed


def cell_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def read_workbook(content, extension):
    """Keep sheet order/names, empty sheets, coordinates, formula text and cached values."""
    sheets = []
    visited = 0
    if extension == ".xls":
        try:
            import xlrd
            book = xlrd.open_workbook(file_contents=content, on_demand=True)
        except Exception as exc:
            raise RawImportError("A régi XLS fájl nem olvasható. Ellenőrizd a fájlt, vagy mentsd XLSX formátumban.") from exc
        try:
            for index in range(book.nsheets):
                sheet = book.sheet_by_index(index)
                rows = []
                for row_index in range(sheet.nrows):
                    visited += sheet.ncols
                    if visited > MAX_VISITED_CELLS:
                        raise RawImportError("Túl nagy munkalapterület. Távolítsd el a szükségtelen üres sorokat/oszlopokat.")
                    cells = []
                    for column in range(sheet.ncols):
                        cell = sheet.cell(row_index, column)
                        if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                            continue
                        value = xlrd.xldate_as_datetime(cell.value, book.datemode).isoformat() if cell.ctype == xlrd.XL_CELL_DATE else cell.value
                        cells.append({"column": column + 1, "type": str(cell.ctype), "value": cell_value(value)})
                    if cells:
                        rows.append({"id": str(uuid4()), "sourceRowNo": row_index + 1, "cells": cells})
                sheets.append({"id": str(uuid4()), "name": sheet.name, "index": index + 1, "rows": rows})
        finally:
            book.release_resources()
    else:
        try:
            with ZipFile(BytesIO(content)) as archive:
                if sum(member.file_size for member in archive.infolist()) > 100 * 1024 * 1024:
                    raise RawImportError("A kibontott Excel túl nagy (legfeljebb 100 MB).")
            formulas = load_workbook(BytesIO(content), read_only=True, data_only=False)
            try:
                cached = load_workbook(BytesIO(content), read_only=True, data_only=True)
            except Exception:
                formulas.close()
                raise
        except RawImportError:
            raise
        except Exception as exc:
            raise RawImportError("A fájl nem olvasható Excel-munkafüzetként.") from exc
        try:
            for index, sheet in enumerate(formulas.worksheets, 1):
                rows = []
                for row_no, (source, values) in enumerate(zip(sheet.iter_rows(), cached[sheet.title].iter_rows()), 1):
                    visited += len(source)
                    if visited > MAX_VISITED_CELLS:
                        raise RawImportError("Túl nagy munkalapterület. Távolítsd el a szükségtelen üres sorokat/oszlopokat.")
                    cells = []
                    for column, cell in enumerate(source, 1):
                        if cell.value is None:
                            continue
                        entry = {"column": column, "type": cell.data_type, "value": cell_value(cell.value)}
                        if cell.data_type == "f":
                            entry["cachedValue"] = cell_value(values[column - 1].value)
                        cells.append(entry)
                    if cells:
                        rows.append({"id": str(uuid4()), "sourceRowNo": row_no, "cells": cells})
                sheets.append({"id": str(uuid4()), "name": sheet.title, "index": index, "rows": rows})
        except RawImportError:
            raise
        except Exception as exc:
            raise RawImportError("Az Excel beolvasása megszakadt; nem jelöltük sikeres mentésnek.") from exc
        finally:
            formulas.close()
            cached.close()
    raw = {"formatVersion": 1, "sheets": sheets}
    if not sheets:
        raise RawImportError("A fájlban nincs munkalap.")
    if len(json.dumps(raw, ensure_ascii=False).encode("utf-8")) > MAX_RAW_BYTES:
        raise RawImportError("A RAW tartalom túl nagy (legfeljebb 25 MB).")
    return raw


def existing_upload(client, request_id):
    try:
        result = client.schema("public").table(TABLE).select(METADATA_FIELDS).eq("id", str(request_id)).limit(1).execute().data or []
        return result[0] if result else None
    except Exception as exc:
        raise database_error(exc) from exc


def verify_existing(row, month, name, sha256, size):
    if (str(row.get("settlement_month"))[:10] != month.isoformat() or row.get("source_file_name") != name
        or row.get("file_sha256") != sha256 or row.get("file_size_bytes") != size):
        raise RawImportError("A kérésazonosító már másik fájlhoz vagy hónaphoz tartozik.", 409)
    return row


def save_workbook(client, content, filename, month, request_id, actor):
    request_id = str(UUID(str(request_id)))
    month = month_start(month)
    name = PureWindowsPath(str(filename or "").replace("/", "\\")).name[:255]
    extension = PureWindowsPath(name).suffix.lower()
    if extension not in {".xlsx", ".xlsm", ".xls"}:
        raise RawImportError("Csak XLSX, XLSM vagy XLS Excel tölthető fel.")
    if not content or len(content) > MAX_FILE_BYTES:
        raise RawImportError("Nem üres, legfeljebb 10 MB méretű Excel tölthető fel.")
    digest = hashlib.sha256(content).hexdigest()
    existing = existing_upload(client, request_id)
    if existing:
        return verify_existing(existing, month, name, digest, len(content))
    raw = read_workbook(content, extension)
    original_path = f"{PREFIX}/{request_id}/original{extension}"
    try:
        bucket = client.storage.get_bucket(BUCKET)
        public = bucket.get("public") if isinstance(bucket, dict) else getattr(bucket, "public", None)
        if public is not False:
            raise RawImportError("Az eredeti Excel mentéséhez privát tárhely szükséges.", 503)
        try:
            client.storage.from_(BUCKET).upload(original_path, content,
                file_options={"content-type": "application/octet-stream", "upsert": "false"})
        except Exception:
            # A lost upload response / retry can leave the same original object in Storage.
            original = client.storage.from_(BUCKET).download(original_path)
            if hashlib.sha256(original).hexdigest() != digest:
                raise RawImportError("Az eredeti fájl tárolása nem igazolható; a korábbi fájlt nem írjuk felül.", 409)
    except RawImportError:
        raise
    except Exception as exc:
        raise RawImportError("Az eredeti Excel mentése nem sikerült. A RAW feltöltés nem lett sikeresnek jelölve.", 502) from exc
    try:
        result = client.schema("public").rpc("pwa_invoice_raw_save", {
            "p_id": request_id, "p_month": month.isoformat(), "p_file_name": name,
            "p_storage_path": original_path, "p_sha256": digest, "p_byte_size": len(content),
            "p_raw_data": raw, "p_created_by": str(actor or "admin"),
        }).execute().data
        if isinstance(result, list):
            result = result[0] if result else None
        if result and result.get("id") == request_id and result.get("status") == "saved":
            return result
        raise RuntimeError("Unconfirmed RAW save")
    except Exception as exc:
        # Never delete an original after an ambiguous DB response: the transaction may have committed.
        confirmed = existing_upload(client, request_id)
        if confirmed:
            return verify_existing(confirmed, month, name, digest, len(content))
        raise database_error(exc) from exc


def list_workbooks(client, month, offset=0, limit=50):
    month = month_start(month)
    try:
        rows = client.schema("public").table(TABLE).select(METADATA_FIELDS).eq("settlement_month", month.isoformat()).order("created_at", desc=True).order("id").range(offset, offset + limit).execute().data or []
        return {"month": month.strftime("%Y-%m"), "items": rows[:limit], "hasMore": len(rows) > limit}
    except Exception as exc:
        raise database_error(exc) from exc
