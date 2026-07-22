from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
import requests

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


ITEM_TABLES = {
    "bonus": "cfg_coordinator_bonus_items",
    "malus": "cfg_coordinator_malus_items",
}
ENTRY_TABLES = {
    "bonus": "ops_coordinator_bonus_entries",
    "malus": "ops_coordinator_malus_entries",
}
RULE_TABLE = "cfg_jitt_compensation_rules"


def _table(mapping: dict[str, str], kind: str) -> str:
    kind = str(kind or "").strip().lower()
    if kind not in mapping:
        raise ValueError("A típus csak bonus vagy malus lehet.")
    return mapping[kind]


def _headers(prefer: str = "") -> dict[str, str]:
    _url, key = get_supabase_config()
    if not key:
        raise RuntimeError("Hiányzik a SUPABASE_SERVICE_ROLE_KEY beállítás.")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _request(
    method: str,
    table: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    prefer: str = "",
) -> list[dict[str, Any]]:
    url, _key = get_supabase_config()
    if not url:
        raise RuntimeError("Hiányzik a SUPABASE_URL beállítás.")
    response = requests.request(
        method,
        f"{url}/rest/v1/{table}",
        headers=_headers(prefer),
        params=params,
        json=payload,
        timeout=45,
    )
    raise_for_supabase_error(response)
    if not response.content:
        return []
    result = response.json()
    return result if isinstance(result, list) else [result]


def read_adjustment_items(kind: str, active_only: bool = True) -> pd.DataFrame:
    params = {
        "select": "id,item_name,default_amount_huf,description,is_active,created_by,created_at,updated_by,updated_at",
        "order": "is_active.desc,item_name.asc",
    }
    if active_only:
        params["is_active"] = "eq.true"
    return pd.DataFrame(_request("GET", _table(ITEM_TABLES, kind), params=params))


def create_adjustment_item(
    kind: str,
    item_name: str,
    default_amount_huf: int,
    description: str,
    actor: str,
) -> dict[str, Any]:
    item_name = str(item_name or "").strip()
    if not item_name:
        raise ValueError("A tétel neve kötelező.")
    rows = _request(
        "POST",
        _table(ITEM_TABLES, kind),
        payload={
            "item_name": item_name,
            "default_amount_huf": abs(int(default_amount_huf or 0)),
            "description": str(description or "").strip(),
            "is_active": True,
            "created_by": str(actor or "admin").strip(),
        },
        prefer="return=representation",
    )
    return rows[0]


def set_adjustment_item_active(kind: str, item_id: str, active: bool, actor: str) -> None:
    _request(
        "PATCH",
        _table(ITEM_TABLES, kind),
        params={"id": f"eq.{item_id}"},
        payload={
            "is_active": bool(active),
            "updated_by": str(actor or "admin").strip(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )


def read_adjustment_entries(
    kind: str,
    *,
    include_deleted: bool = False,
    limit: int = 250,
) -> pd.DataFrame:
    params = {
        "select": (
            "id,courier_id,courier_name,item_id,item_name,amount_huf,note,effective_date,"
            "recorded_by,recorded_at,deleted_at,deleted_by,delete_reason"
        ),
        "order": "recorded_at.desc",
        "limit": str(int(limit)),
    }
    if not include_deleted:
        params["deleted_at"] = "is.null"
    return pd.DataFrame(_request("GET", _table(ENTRY_TABLES, kind), params=params))


def create_adjustment_entry(
    kind: str,
    courier_id: str,
    courier_name: str,
    item_id: str,
    item_name: str,
    amount_huf: int,
    note: str,
    effective_date: date,
    actor: str,
) -> dict[str, Any]:
    if not str(courier_id or "").strip() or not str(courier_name or "").strip():
        raise ValueError("Futár kiválasztása kötelező.")
    amount = abs(int(amount_huf or 0))
    if amount <= 0:
        raise ValueError("Az összegnek nagyobbnak kell lennie nullánál.")
    rows = _request(
        "POST",
        _table(ENTRY_TABLES, kind),
        payload={
            "courier_id": str(courier_id).strip(),
            "courier_name": str(courier_name).strip(),
            "item_id": str(item_id or "").strip() or None,
            "item_name": str(item_name or "").strip(),
            "amount_huf": amount,
            "note": str(note or "").strip(),
            "effective_date": effective_date.isoformat(),
            "recorded_by": str(actor or "unknown").strip(),
        },
        prefer="return=representation",
    )
    return rows[0]


def soft_delete_adjustment_entry(
    kind: str,
    entry_id: str,
    actor: str,
    reason: str,
) -> None:
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("A visszavonás indoklása kötelező.")
    _request(
        "PATCH",
        _table(ENTRY_TABLES, kind),
        params={"id": f"eq.{entry_id}", "deleted_at": "is.null"},
        payload={
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "deleted_by": str(actor or "unknown").strip(),
            "delete_reason": reason,
        },
        prefer="return=minimal",
    )


def read_compensation_rules(active_only: bool = False) -> pd.DataFrame:
    params = {
        "select": "*",
        "order": "is_active.desc,valid_from.desc,rule_category.asc,rule_name.asc",
    }
    if active_only:
        params["is_active"] = "eq.true"
    return pd.DataFrame(_request("GET", RULE_TABLE, params=params))


def create_compensation_rule(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    clean_payload = dict(payload)
    clean_payload["created_by"] = str(actor or "admin").strip()
    clean_payload["updated_by"] = str(actor or "admin").strip()
    rows = _request(
        "POST",
        RULE_TABLE,
        payload=clean_payload,
        prefer="return=representation",
    )
    return rows[0]


def set_compensation_rule_active(rule_id: str, active: bool, actor: str) -> None:
    _request(
        "PATCH",
        RULE_TABLE,
        params={"id": f"eq.{rule_id}"},
        payload={
            "is_active": bool(active),
            "updated_by": str(actor or "admin").strip(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        prefer="return=minimal",
    )
