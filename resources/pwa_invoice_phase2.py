"""RAW comparison and isolated monthly working copies. Never calculates a settlement."""
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from uuid import UUID
from threading import BoundedSemaphore

from resources.pwa_invoice_raw import RawImportError, month_start, METADATA_FIELDS, TABLE

COMPARISON_SLOT = BoundedSemaphore(1)

WORK_TABLE = "PWA_INVOICE_WORK"
WORK_FIELDS = "settlement_month,id,session_id,source_upload_id,source_session_id,source_file_name,file_sha256,sheet_count,raw_row_count,created_by,created_at"


def process_memory_mb():
    try:
        line = next(line for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("VmRSS:"))
        return round(int(line.split()[1]) / 1024, 1)
    except (OSError, StopIteration, ValueError):
        return None


def db_call(operation):
    try:
        return operation()
    except RawImportError:
        raise
    except Exception as exc:
        if any(code in str(exc) for code in ("PGRST205", "PGRST202", "42P01", "42883", "42703")):
            raise RawImportError("A Phase 2 tároló még nincs telepítve. Futtasd a sql/pwa_invoice_phase2.sql fájlt a Supabase SQL Editorban.", 503) from exc
        raise RawImportError("Az adatbázis-művelet eredménye nem igazolható. Frissítsd a listát az újrapróbálás előtt.", 502) from exc


def upload_ids(values, minimum=1, maximum=10):
    ids = list(dict.fromkeys(str(UUID(str(value))) for value in values))
    if not minimum <= len(ids) <= maximum:
        raise RawImportError(f"Legalább {minimum}, legfeljebb {maximum} különböző fájl választható.")
    return ids


def read_sources(client, month, ids):
    rows = db_call(lambda: client.schema("public").table(TABLE).select(METADATA_FIELDS)
                   .eq("settlement_month", month_start(month).isoformat()).is_("deleted_at", "null")
                   .in_("id", ids).execute().data or [])
    by_id = {str(row["id"]): row for row in rows}
    if set(by_id) != set(ids):
        raise RawImportError("Egy kiválasztott fájl hiányzik, törölt vagy másik hónaphoz tartozik. Frissítsd a listát.", 409)
    return [by_id[id] for id in ids]


def read_sheet_catalog(client, month, sources):
    ids = [str(source["id"]) for source in sources]
    catalog = {id: {} for id in ids}
    largest = max(int(source["sheet_count"]) for source in sources)
    # Bounded URL length; only names travel over the wire, never all RAW sheets.
    for start in range(0, largest, 16):
        indexes = range(start, min(start + 16, largest))
        fields = "id," + ",".join(f"s{i}:raw_data->sheets->{i}->name" for i in indexes)
        rows = db_call(lambda: client.schema("public").table(TABLE).select(fields)
            .eq("settlement_month", month_start(month).isoformat()).is_("deleted_at", "null")
            .in_("id", ids).execute().data or [])
        if {str(row["id"]) for row in rows} != set(ids):
            raise RawImportError("Egy forrás közben megváltozott. Frissítsd a feltöltési listát.", 409)
        for row in rows:
            for i in indexes:
                name = row.get(f"s{i}")
                if name is not None:
                    catalog[str(row["id"])][name] = i
    if any(len(catalog[str(source["id"])]) != int(source["sheet_count"]) for source in sources):
        raise RawImportError("A munkalaplista nem egyezik a feltöltés adataival.", 409)
    return catalog


def read_source_sheet(client, month, source_id, index, expected_name):
    rows = db_call(lambda: client.schema("public").table(TABLE)
        .select(f"id,sheet:raw_data->sheets->{index}").eq("id", str(source_id))
        .eq("settlement_month", month_start(month).isoformat()).is_("deleted_at", "null")
        .limit(1).execute().data or [])
    sheet = rows[0].get("sheet") if rows else None
    if not sheet or sheet.get("name") != expected_name:
        raise RawImportError("A kiválasztott munkalap közben nem elérhető. Frissítsd a listát.", 409)
    return sheet


def canonical(value):
    def normalize(item):
        if isinstance(item, float) and item.is_integer(): return int(item)
        if isinstance(item, dict): return {key: normalize(val) for key, val in item.items()}
        if isinstance(item, list): return [normalize(val) for val in item]
        return item
    return json.dumps(normalize(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def cells(row):
    # UUIDs and source row coordinates are provenance, not Excel contents.
    return {int(cell["column"]): {key: cell[key] for key in ("type", "value", "cachedValue") if key in cell}
            for cell in row.get("cells", [])}


def column_name(number):
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def changed_cells(left, right):
    a, b = cells(left), cells(right)
    output = []
    for col in sorted(set(a) | set(b)):
        if canonical(a.get(col)) == canonical(b.get(col)):
            continue
        item = {"column": col, "columnName": column_name(col), "before": a.get(col), "after": b.get(col)}
        av, bv = a.get(col, {}).get("value"), b.get(col, {}).get("value")
        if isinstance(av, (int, float)) and not isinstance(av, bool) and isinstance(bv, (int, float)) and not isinstance(bv, bool):
            try:
                delta = Decimal(str(bv)) - Decimal(str(av))
                if delta.is_finite(): item["delta"] = str(delta)
            except InvalidOperation:
                pass
        output.append(item)
    return output


def compare_sheet(left, right, key_columns=None, offset=0, limit=50, include_details=False):
    a, b = (left or {}).get("rows", []), (right or {}).get("rows", [])
    pool = defaultdict(deque)
    for index, row in enumerate(b):
        pool[canonical(cells(row))].append(index)
    used = set()
    unmatched_a = []
    same = moved = 0
    for row in a:
        match = pool[canonical(cells(row))]
        if match:
            other = b[match.popleft()]
            # Record the exact instance to retain duplicate-row multiplicity.
            same += 1
            if row.get("sourceRowNo") != other.get("sourceRowNo"): moved += 1
        else:
            unmatched_a.append(row)
    for queue in pool.values():
        used.update(queue)
    unmatched_b = [row for index, row in enumerate(b) if index in used]
    pairs, warning = [], ""
    if key_columns:
        def key(row):
            value = cells(row)
            if any(col not in value or value[col].get("value") in (None, "") for col in key_columns): return None
            return canonical([value[col] for col in key_columns])
        # Require uniqueness across all rows, not merely the unmatched subset.
        all_a, all_b = defaultdict(list), defaultdict(list)
        for row in a: all_a[key(row)].append(row)
        for row in b: all_b[key(row)].append(row)
        if any(len(rows) > 1 for mapping in (all_a, all_b) for k, rows in mapping.items() if k is not None):
            warning = "A kulcs nem egyedi. A nem egyező sorokat külön hiányzó/új sorként mutatjuk; válassz egyedi kulcsoszlopokat."
        else:
            b_keys = {key(row): row for row in unmatched_b if key(row) is not None}
            paired_a, paired_b = set(), set()
            for row in unmatched_a:
                other = b_keys.get(key(row)) if key(row) is not None else None
                if other is not None:
                    pairs.append((row, other, "key"))
                    paired_a.add(id(row)); paired_b.add(id(other))
            unmatched_a = [row for row in unmatched_a if id(row) not in paired_a]
            unmatched_b = [row for row in unmatched_b if id(row) not in paired_b]
    elif len(unmatched_a) == len(unmatched_b) and unmatched_a:
        pairs = [(x, y, "suggested") for x, y in zip(unmatched_a, unmatched_b)]
        unmatched_a, unmatched_b = [], []
        warning = "Kulcs nélkül a módosult sorok párosítása javaslat, ellenőrzendő. Pontos párosításhoz adj meg egyedi kulcsoszlopot (például A vagy A,C)."
    elif unmatched_a or unmatched_b:
        warning = "A nem egyező sorokhoz nincs egyedi kulcs: hiányzó és új sorként jelennek meg."
    summary = {"beforeRows": len(a), "afterRows": len(b), "identicalRows": same, "movedRows": moved,
               "changedRows": len(pairs), "removedRows": len(unmatched_a), "addedRows": len(unmatched_b), "warning": warning}
    if not include_details:
        return summary
    def changes():
        for x, y, method in pairs:
            yield {"kind": "changed", "beforeRow": x.get("sourceRowNo"), "afterRow": y.get("sourceRowNo"),
                   "match": method, "cells": changed_cells(x, y)}
        for row in unmatched_a:
            yield {"kind": "removed", "beforeRow": row.get("sourceRowNo"), "cells": changed_cells(row, {})}
        for row in unmatched_b:
            yield {"kind": "added", "afterRow": row.get("sourceRowNo"), "cells": changed_cells({}, row)}
    total = len(pairs) + len(unmatched_a) + len(unmatched_b)
    details = []
    for index, change in enumerate(changes()):
        if index >= offset + limit: break
        if index >= offset: details.append(change)
    return {**summary, "changes": details, "offset": offset, "total": total, "hasMore": offset + len(details) < total}


def compare_workbooks(client, month, selected, primary, key_columns=None, detail_upload_id=None, detail_sheet=None, offset=0, limit=50):
    if not COMPARISON_SLOT.acquire(blocking=False):
        raise RawImportError("Másik összehasonlítás még folyamatban van. Várd meg a végét, majd próbáld újra.", 429)
    try:
        return _compare_workbooks(client, month, selected, primary, key_columns, detail_upload_id, detail_sheet, offset, limit)
    finally:
        COMPARISON_SLOT.release()


def _compare_workbooks(client, month, selected, primary, key_columns=None, detail_upload_id=None, detail_sheet=None, offset=0, limit=50):
    ids = upload_ids(selected, 2)
    primary = str(UUID(str(primary)))
    if primary not in ids:
        raise RawImportError("Az elsődleges fájlt a kijelöltek közül válaszd ki.")
    if detail_upload_id and str(detail_upload_id) not in set(ids) - {primary}:
        raise RawImportError("Érvénytelen összehasonlítási cél.")
    key_columns = key_columns or {}
    if any(not isinstance(cols, list) or len(cols) > 10 or any(not isinstance(col, int) or isinstance(col, bool) or not 1 <= col <= 16384 for col in cols) for cols in key_columns.values()):
        raise RawImportError("A kulcsoszlopok sorszáma 1 és 16384 közé essen (legfeljebb 10 oszlop).")
    sources = read_sources(client, month, ids)
    catalog = read_sheet_catalog(client, month, sources)
    base = catalog[primary]
    others = [source for source in sources if str(source["id"]) != primary]
    output = {str(source["id"]): {"uploadId": source["id"], "fileName": source["source_file_name"], "sheets": []} for source in others}
    names = list(dict.fromkeys([*base, *(name for source in others for name in catalog[str(source["id"])])]))
    if detail_sheet is not None:
        names = [detail_sheet] if detail_sheet in names else []
    for name in names:
        left = read_source_sheet(client, month, primary, base[name], name) if name in base else None
        for source in others:
            source_id = str(source["id"])
            if detail_sheet is not None and source_id != str(detail_upload_id): continue
            target = catalog[source_id]
            if name not in base and name not in target: continue
            right = read_source_sheet(client, month, source_id, target[name], name) if name in target else None
            summary = compare_sheet(left, right, key_columns.get(name), offset, limit, detail_sheet is not None)
            output[source_id]["sheets"].append({"name": name, "status": "added" if left is None else "removed" if right is None else "changed" if summary["changedRows"] + summary["addedRows"] + summary["removedRows"] or summary["movedRows"] or left.get("index") != right.get("index") else "identical",
                "beforeIndex": (left or {}).get("index"), "afterIndex": (right or {}).get("index"), **summary})
            del right
        del left
    return {"ok": True, "primaryId": primary, "comparisons": list(output.values())}


def get_working(client, month, working_id=None, sheet=None, offset=0, limit=30):
    month_filter = month_start(month).isoformat()
    stale_message = "Ez már nem a hónap aktív munkamenete. Lépj vissza és válaszd ki újra a forrást."

    def fetch(fields):
        query = client.schema("public").table(WORK_TABLE).select(fields).eq("settlement_month", month_filter)
        if working_id:
            query = query.eq("id", str(working_id))
        rows = db_call(lambda: query.limit(1).execute().data or [])
        if working_id and (not rows or str(rows[0]["id"]) != str(working_id)):
            raise RawImportError(stale_message, 409)
        return rows[0] if rows else None

    current = fetch(WORK_FIELDS)
    if not working_id:
        return {"ok": True, "working": current}

    sheets = []
    for start in range(0, int(current["sheet_count"]), 16):
        indexes = range(start, min(start + 16, int(current["sheet_count"])))
        fields = "id," + ",".join(f"s{i}:raw_data->sheets->{i}->name" for i in indexes)
        names = fetch(fields)
        sheets.extend({"name": names[f"s{i}"], "index": i + 1} for i in indexes)
    current["sheets"] = sheets

    if sheet is not None:
        chosen = next((entry for entry in sheets if entry["name"] == sheet), None)
        if chosen is None:
            raise RawImportError("A munkalap nem található.", 404)
        sheet_index = chosen["index"] - 1
        preview_rows = []
        # Read one extra row to detect the next page. Bound each query URL.
        for start in range(offset, offset + limit + 1, 16):
            indexes = range(start, min(start + 16, offset + limit + 1))
            fields = "id," + ",".join(f"r{i}:raw_data->sheets->{sheet_index}->rows->{i}" for i in indexes)
            page = fetch(fields)
            preview_rows.extend(page[f"r{i}"] for i in indexes if page.get(f"r{i}") is not None)
            if page.get(f"r{indexes[-1]}") is None:
                break
        current["preview"] = {"sheet": sheet, "rows": preview_rows[:limit], "hasMore": len(preview_rows) > limit}
    return {"ok": True, "working": current}


def select_working(client, month, source_id, request_id, expected_id, actor):
    data = db_call(lambda: client.schema("public").rpc("pwa_invoice_work_select", {
        "p_month": month_start(month).isoformat(), "p_source_id": str(source_id),
        "p_request_id": str(request_id), "p_expected_id": str(expected_id) if expected_id else None,
        "p_actor": str(actor or "admin"),
    }).execute().data)
    if data and data.get("conflict"):
        raise RawImportError("A hónap munkapéldánya közben megváltozott. Lépj vissza és ellenőrizd az aktuális előszobát.", 409)
    if data and data.get("missing"):
        raise RawImportError("A kiválasztott fájl már nem elérhető ebben a hónapban.", 409)
    if not data or str(data.get("source_upload_id")) != str(source_id) or not data.get("id"):
        raise RawImportError("Az előszobai másolat mentése nem igazolható.", 502)
    return {"ok": True, "working": data}


def delete_sources(client, month, ids):
    ids = upload_ids(ids, maximum=100)
    data = db_call(lambda: client.schema("public").rpc("pwa_invoice_raw_delete", {
        "p_month": month_start(month).isoformat(), "p_ids": ids,
    }).execute().data)
    if data and data.get("activeSource"):
        raise RawImportError("Az aktív előszobai munkapéldány forrását nem lehet törölni. Először válassz másik forrást.", 409)
    if data and data.get("missing"):
        raise RawImportError("A törlésre kijelölt fájlok nem mind ehhez a hónaphoz tartoznak.", 409)
    if not data or not data.get("ok"):
        raise RawImportError("A törlés nem igazolható. Frissítsd a listát.", 502)
    return data
