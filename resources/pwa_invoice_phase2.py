"""RAW comparison and isolated monthly working copies. Never calculates a settlement."""
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
import json
from uuid import UUID

from resources.pwa_invoice_raw import RawImportError, month_start, METADATA_FIELDS, TABLE

WORK_TABLE = "PWA_INVOICE_WORK"
WORK_FIELDS = "settlement_month,id,session_id,source_upload_id,source_session_id,source_file_name,file_sha256,sheet_count,raw_row_count,created_by,created_at"


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
    rows = db_call(lambda: client.schema("public").table(TABLE).select(METADATA_FIELDS + ",raw_data")
                   .eq("settlement_month", month_start(month).isoformat()).is_("deleted_at", "null")
                   .in_("id", ids).execute().data or [])
    by_id = {str(row["id"]): row for row in rows}
    if set(by_id) != set(ids):
        raise RawImportError("Egy kiválasztott fájl hiányzik, törölt vagy másik hónaphoz tartozik. Frissítsd a listát.", 409)
    return [by_id[id] for id in ids]


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
    ids = upload_ids(selected, 2)
    primary = str(UUID(str(primary)))
    if primary not in ids:
        raise RawImportError("Az elsődleges fájlt a kijelöltek közül válaszd ki.")
    if detail_upload_id and str(detail_upload_id) not in set(ids) - {primary}:
        raise RawImportError("Érvénytelen összehasonlítási cél.")
    sources = read_sources(client, month, ids)
    base = next(row for row in sources if row["id"] == primary)
    sheets = {s["name"]: s for s in base["raw_data"]["sheets"]}
    output = []
    key_columns = key_columns or {}
    if any(not isinstance(cols, list) or len(cols) > 10 or any(not isinstance(col, int) or isinstance(col, bool) or not 1 <= col <= 16384 for col in cols) for cols in key_columns.values()):
        raise RawImportError("A kulcsoszlopok sorszáma 1 és 16384 közé essen (legfeljebb 10 oszlop).")
    for source in sources:
        if source["id"] == primary: continue
        others = {s["name"]: s for s in source["raw_data"]["sheets"]}
        result = []
        for name in dict.fromkeys([*sheets, *others]):
            if detail_sheet is not None and (name != detail_sheet or str(source["id"]) != str(detail_upload_id)): continue
            left, right = sheets.get(name), others.get(name)
            summary = compare_sheet(left, right, key_columns.get(name), offset, limit, detail_sheet is not None)
            result.append({"name": name, "status": "added" if left is None else "removed" if right is None else "changed" if summary["changedRows"] + summary["addedRows"] + summary["removedRows"] or summary["movedRows"] or left.get("index") != right.get("index") else "identical",
                           "beforeIndex": (left or {}).get("index"), "afterIndex": (right or {}).get("index"), **summary})
        output.append({"uploadId": source["id"], "fileName": source["source_file_name"], "sheets": result})
    return {"ok": True, "primaryId": primary, "comparisons": output}


def get_working(client, month, working_id=None, sheet=None, offset=0, limit=30):
    fields = WORK_FIELDS + (",raw_data" if working_id else "")
    rows = db_call(lambda: client.schema("public").table(WORK_TABLE).select(fields)
                  .eq("settlement_month", month_start(month).isoformat()).limit(1).execute().data or [])
    current = rows[0] if rows else None
    if working_id:
        if not current or str(current["id"]) != str(working_id):
            raise RawImportError("Ez már nem a hónap aktív munkamenete. Lépj vissza és válaszd ki újra a forrást.", 409)
        raw = current.pop("raw_data")
        current["sheets"] = [{"name": s["name"], "rowCount": len(s["rows"]), "index": s.get("index")} for s in raw["sheets"]]
        if sheet is not None:
            chosen = next((s for s in raw["sheets"] if s["name"] == sheet), None)
            if chosen is None: raise RawImportError("A munkalap nem található.", 404)
            current["preview"] = {"sheet": sheet, "rows": chosen["rows"][offset:offset + limit], "hasMore": len(chosen["rows"]) > offset + limit}
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
