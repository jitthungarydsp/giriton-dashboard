from __future__ import annotations

from datetime import date, datetime, time, timedelta
from html import escape
import os
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlencode
import uuid

import pandas as pd
import requests
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from resources.foglalasok_db import read_foglalasok_raw
from resources.giriton_auto_booking import read_giriton_booking_log
from resources.giriton_shifts_db import read_giriton_shifts_raw
from resources.shift_comparison_db import read_next_5_day_shift_comparison

try:
    from resources import github_actions as _github_actions

    GitHubActionsError = getattr(_github_actions, "GitHubActionsError", RuntimeError)
    dispatch_workflow = getattr(_github_actions, "dispatch_workflow", None)
except Exception as exc:  # pragma: no cover - keeps the page readable during deploy drift
    class GitHubActionsError(Exception):
        pass

    dispatch_workflow = None
    _GITHUB_ACTIONS_IMPORT_ERROR = exc
else:
    _GITHUB_ACTIONS_IMPORT_ERROR = None


MIN_SHIFT_GAP_MINUTES = 270
GITHUB_OWNER_DEFAULT = "jitthungarydsp"
GITHUB_REPO_DEFAULT = "giriton-dashboard"
GITHUB_REF_DEFAULT = "main"
AUTO_BOOKING_WORKFLOW = "giriton-auto-booking.yml"


def _clean(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value or "").strip()


def _secret(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value

    try:
        return str(st.secrets.get(name, default) or "")
    except Exception:
        return default


def _github_token_candidates() -> list[tuple[str, str]]:
    tokens = []
    seen = set()
    for name in ["GITHUB_ACTIONS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT"]:
        value = _secret(name)
        if not value or value in seen:
            continue
        tokens.append((name, value))
        seen.add(value)
    return tokens


def _dispatch_workflow_fallback(workflow: str, inputs: dict[str, str]) -> dict[str, str]:
    token_candidates = _github_token_candidates()
    if not token_candidates:
        raise GitHubActionsError(
            "Hiányzik a GitHub token secret. Add meg valamelyiket: GITHUB_ACTIONS_TOKEN, GITHUB_TOKEN, GH_TOKEN vagy GITHUB_PAT."
        )

    owner = _secret("GITHUB_OWNER", GITHUB_OWNER_DEFAULT)
    repo = _secret("GITHUB_REPO", GITHUB_REPO_DEFAULT)
    ref = _secret("GITHUB_REF", GITHUB_REF_DEFAULT)
    workflow_name = workflow or AUTO_BOOKING_WORKFLOW
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_name}/dispatches"
    response = None
    used_secret_name = ""
    for secret_name, token in token_candidates:
        used_secret_name = secret_name
        response = requests.post(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "ref": ref,
                "inputs": {key: str(value) for key, value in inputs.items()},
            },
            timeout=20,
        )
        if response.status_code == 204:
            break
        if response.status_code != 401:
            break

    if response is None:
        raise GitHubActionsError("GitHub Actions indítás sikertelen: nincs HTTP válasz.")

    if response.status_code != 204:
        if response.status_code == 401:
            tried = ", ".join(name for name, _token in token_candidates)
            raise GitHubActionsError(
                "GitHub Actions indítás sikertelen: minden megadott GitHub token hibás vagy lejárt. "
                f"Próbált secret(ek): {tried}."
            )
        raise GitHubActionsError(
            f"GitHub Actions indítás sikertelen ({used_secret_name}): HTTP {response.status_code} - {response.text[:500]}"
        )

    return {
        "workflow": workflow_name,
        "ref": ref,
        "triggered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _github_request_with_tokens(method: str, url: str, **kwargs):
    token_candidates = _github_token_candidates()
    if not token_candidates:
        raise GitHubActionsError(
            "Hiányzik a GitHub token secret. Add meg valamelyiket: GITHUB_ACTIONS_TOKEN, GITHUB_TOKEN, GH_TOKEN vagy GITHUB_PAT."
        )

    response = None
    used_secret_name = ""
    for secret_name, token in token_candidates:
        used_secret_name = secret_name
        response = requests.request(
            method,
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=20,
            **kwargs,
        )
        if response.status_code != 401:
            return response, used_secret_name

    tried = ", ".join(name for name, _token in token_candidates)
    raise GitHubActionsError(
        "GitHub Actions állapot lekérés sikertelen: minden megadott GitHub token hibás vagy lejárt. "
        f"Próbált secret(ek): {tried}."
    )


def _latest_auto_booking_runs(limit: int = 5) -> list[dict]:
    owner = _secret("GITHUB_OWNER", GITHUB_OWNER_DEFAULT)
    repo = _secret("GITHUB_REPO", GITHUB_REPO_DEFAULT)
    url = (
        f"https://api.github.com/repos/{owner}/{repo}"
        f"/actions/workflows/{AUTO_BOOKING_WORKFLOW}/runs"
    )
    response, used_secret_name = _github_request_with_tokens(
        "GET",
        url,
        params={"per_page": int(limit)},
    )
    if response.status_code != 200:
        raise GitHubActionsError(
            f"GitHub Actions állapot lekérés sikertelen ({used_secret_name}): HTTP {response.status_code} - {response.text[:500]}"
        )
    return response.json().get("workflow_runs", [])


def _github_status_label(run: dict) -> str:
    status = _clean(run.get("status")) or "-"
    conclusion = _clean(run.get("conclusion"))
    if status == "completed":
        if conclusion == "success":
            return "Sikeres"
        if conclusion == "failure":
            return "Hibás"
        if conclusion == "cancelled":
            return "Megszakítva"
        return conclusion or "Befejezve"
    if status == "queued":
        return "Sorban"
    if status == "in_progress":
        return "Fut"
    return status


def _format_github_time(value) -> str:
    text = _clean(value)
    if not text:
        return "-"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y.%m.%d. %H:%M:%S")
    except ValueError:
        return text


def _match_text(value) -> str:
    text = unicodedata.normalize("NFKD", _clean(value).casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _worker_match_key(row) -> str:
    courier_id = _clean(row.get("courier_id"))
    if re.fullmatch(r"\d+\.0+", courier_id):
        courier_id = courier_id.split(".", 1)[0]
    if courier_id:
        return f"id:{courier_id}"

    worker = _match_text(row.get("courier_name"))
    return f"name:{worker}" if worker else ""


def _booking_worker_match_key(row) -> str:
    courier_id = _clean(row.get("courier_id"))
    if re.fullmatch(r"\d+\.0+", courier_id):
        courier_id = courier_id.split(".", 1)[0]
    if courier_id:
        return f"id:{courier_id}"

    email = _clean(row.get("email")).casefold()
    if email:
        return f"email:{email}"

    return ""


def _warehouse_match_key(value) -> str:
    return _match_text(value)


def _optional_int(value) -> int | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _giriton_capacity(row) -> tuple[int | None, int | None]:
    booked = _optional_int(row.get("booked"))
    maximum = _optional_int(row.get("maximum"))

    if booked is not None and maximum is not None:
        return booked, maximum

    occupancy = _clean(row.get("occupancy"))
    match = re.search(r"(\d+)\s*/\s*(\d+)", occupancy)
    if match:
        return int(match.group(1)), int(match.group(2))

    return booked, maximum


def _has_open_giriton_capacity(row) -> bool:
    booked, maximum = _giriton_capacity(row)
    if maximum is None:
        return False
    booked = booked or 0
    return maximum > booked


def _is_available_giriton_shift(row) -> bool:
    return not _is_booked_giriton_shift(row) and _has_open_giriton_capacity(row)


def _is_booked_giriton_shift(row) -> bool:
    status = _clean(row.get("status")).upper()
    worker_key = _match_text(row.get("courier_name"))
    courier_id = _clean(row.get("courier_id"))
    email = _clean(row.get("email"))
    booked, _maximum = _giriton_capacity(row)

    if booked == 0:
        return False
    if worker_key in {"", "ures", "none", "null"} or "none" in worker_key:
        return False
    if not courier_id and not email:
        return False
    if status in {"", "URES", "ÜRES", "NONE", "NULL", "-"}:
        return False
    if booked is not None and booked > 0:
        return True

    return False


def _format_latest(value: str) -> str:
    text = _clean(value)
    if not text:
        return "-"

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y.%m.%d. %H:%M:%S")
    except ValueError:
        return text


def _latest(df: pd.DataFrame, column: str) -> str:
    if df.empty or column not in df.columns:
        return "-"

    values = [
        _clean(value)
        for value in df[column].dropna().astype(str).tolist()
        if _clean(value)
    ]
    return _format_latest(max(values)) if values else "-"


def _normalize_time(value) -> str:
    text = _clean(value)
    if not text:
        return ""

    parts = text.split(":")
    if len(parts) >= 2:
        try:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except ValueError:
            return text

    return text


def _shift_start(shift_text) -> str:
    text = _clean(shift_text)
    if not text:
        return ""

    match = re.search(r"(\d{1,2}:\d{2})", text)
    if match:
        return _normalize_time(match.group(1))

    return ""


def _parse_time(value) -> time | None:
    text = _normalize_time(value)
    if not text:
        return None

    try:
        return datetime.strptime(text, "%H:%M").time()
    except ValueError:
        return None


def _in_time_range(value, start_time: time, end_time: time) -> bool:
    parsed = _parse_time(value)
    if parsed is None:
        return True

    if start_time <= end_time:
        return start_time <= parsed <= end_time

    return parsed >= start_time or parsed <= end_time


def _filter_time(df: pd.DataFrame, column: str, start_time: time, end_time: time) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df

    return df[df[column].map(lambda value: _in_time_range(value, start_time, end_time))]


def _time_minutes(value) -> int | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None

    return parsed.hour * 60 + parsed.minute


def _diff_minutes(left, right) -> int | None:
    left_minutes = _time_minutes(left)
    right_minutes = _time_minutes(right)
    if left_minutes is None or right_minutes is None:
        return None

    diff = right_minutes - left_minutes
    if diff > 720:
        diff -= 1440
    elif diff < -720:
        diff += 1440
    return diff


def _shift_gap_ok(times: list[str]) -> bool:
    minutes = sorted(
        minute
        for minute in (_time_minutes(value) for value in times)
        if minute is not None
    )
    if len(minutes) <= 1:
        return True

    return all(
        current - previous >= MIN_SHIFT_GAP_MINUTES
        for previous, current in zip(minutes, minutes[1:])
    )


def _apply_worker(df: pd.DataFrame, worker: str) -> pd.DataFrame:
    if worker == "Összes dolgozó" or df.empty or "courier_name" not in df.columns:
        return df

    return df[df["courier_name"].fillna("").astype(str) == worker]


def _worker_options(*frames: pd.DataFrame) -> list[str]:
    names: set[str] = set()
    for df in frames:
        if not df.empty and "courier_name" in df.columns:
            names.update(
                _clean(value)
                for value in df["courier_name"].dropna().unique()
                if _clean(value)
            )

    return ["Összes dolgozó", *sorted(names)]


def _status_count(df: pd.DataFrame, value: str) -> int:
    if df.empty or "missing_source" not in df.columns:
        return 0

    has_missing = df["missing_source"].fillna("").astype(str).str.strip() != ""
    return int(has_missing.sum()) if value == "missing" else int((~has_missing).sum())


def _status_badge(status: str) -> str:
    classes = {
        "Egyezés": "ok",
        "Alternatíva": "warn",
        "Sikertelen": "bad",
        "Lefoglalva": "booked",
    }
    class_name = classes.get(status, "neutral")
    return f"<span class='status-badge {class_name}'>{escape(status)}</span>"


def _action_badge(status: str) -> str:
    labels = {
        "Egyezés": "Foglalás",
        "Alternatíva": "Ellenőrzés",
        "Sikertelen": "Kézi döntés",
        "Lefoglalva": "Kész",
        "Indítva": "Indítva",
    }
    class_name = {
        "Egyezés": "ok",
        "Alternatíva": "warn",
        "Sikertelen": "bad",
        "Lefoglalva": "booked",
        "Indítva": "booked disabled",
    }.get(status, "neutral")
    return f"<span class='action-badge {class_name}'>{escape(labels.get(status, '-'))}</span>"


def _started_booking_serials() -> set[str]:
    return set(st.session_state.get("foglalas_started_serials", []))


def _mark_booking_started(serial: str) -> None:
    serial = _clean(serial)
    if not serial:
        return
    started = _started_booking_serials()
    started.add(serial)
    st.session_state["foglalas_started_serials"] = sorted(started)


def _booking_action_identity(row: dict) -> dict[str, str]:
    return {
        "serial": _clean(row.get("Serial")),
        "work_date": _clean(row.get("Dátum")),
        "worker": _clean(row.get("Dolgozó")),
        "warehouse": _clean(row.get("Raktár")).upper(),
        "shift_start": _clean(row.get("MűszakPro")),
    }


def _remember_booking_action(identity: dict[str, str]) -> str:
    token = uuid.uuid4().hex
    actions = st.session_state.setdefault("foglalas_booking_actions", {})
    actions[token] = identity
    if len(actions) > 1000:
        for stale_token in list(actions)[:-1000]:
            actions.pop(stale_token, None)
    return token


def _booking_action_badge(row: dict) -> str:
    status = _clean(row.get("Állapot"))
    if status != "Egyezés":
        return _action_badge(status)

    identity = _booking_action_identity(row)
    serial = identity["serial"]
    work_date = identity["work_date"]
    if not serial or not work_date:
        return _action_badge(status)
    if serial in _started_booking_serials():
        return "<span class='action-badge booked disabled'>Indítva</span>"

    action_token = _remember_booking_action(identity)
    query = urlencode(
        {
            "foglalas_action": "book_serial",
            "action_token": action_token,
            "serial": serial,
            "work_date": work_date,
            "worker": identity["worker"],
            "warehouse": identity["warehouse"],
            "shift_start": identity["shift_start"],
        }
    )
    return (
        f"<a class='action-badge ok action-link' href='?{query}' "
        f"title='Éles Giriton foglalás indítása serial alapján'>Foglalás</a>"
    )


def _giriton_state_badge(status: str) -> str:
    class_name = {
        "Nincs lefoglalva": "warn",
        "Lefoglalva": "booked",
    }.get(status, "neutral")
    return f"<span class='status-badge {class_name}'>{escape(status or '-')}</span>"


def _cell_class(row, column: str) -> str:
    status = _clean(row.get("Állapot"))
    diff_text = _clean(row.get("Eltérés"))
    giriton_booking = _clean(row.get("Giriton foglalás"))
    giriton_offer = _clean(row.get("Giriton ajánlat"))
    has_giriton_time = bool(
        (giriton_booking and giriton_booking != "-")
        or (giriton_offer and giriton_offer != "-" and not giriton_offer.lower().startswith("nincs"))
    )
    if column == "MűszakPro" and diff_text == "0 perc":
        return "match-ok"
    if column == "MűszakPro" and status in {"Alternatíva", "Lefoglalva"} and diff_text not in {"", "-", "0 perc"} and has_giriton_time:
        return "booked-conflict"
    if column == "Giriton foglalás" and status == "Lefoglalva" and giriton_booking and giriton_booking != "-":
        return "match-ok" if diff_text == "0 perc" else "booked-ok"
    if column == "Giriton ajánlat" and status in {"Egyezés", "Alternatíva"} and giriton_offer and giriton_offer != "-":
        return "match-ok"
    return ""


def _time_list(values) -> str:
    times = sorted(
        {
            _normalize_time(value)
            for value in values
            if _normalize_time(value)
        }
    )
    return ", ".join(times) if times else "-"


def _group_shifts(df: pd.DataFrame, time_column: str) -> dict[tuple[str, str, str], dict]:
    if df.empty or time_column not in df.columns:
        return {}

    groups: dict[tuple[str, str, str], dict] = {}
    for _, row in df.iterrows():
        worker = _clean(row.get("courier_name"))
        if not worker or worker.upper() == "URES":
            continue

        worker_key = _worker_match_key(row)
        if not worker_key:
            continue

        warehouse = _clean(row.get("warehouse"))
        key = (
            _clean(row.get("work_date")),
            worker_key,
            _warehouse_match_key(warehouse),
        )
        group = groups.setdefault(
            key,
            {
                "times": [],
                "records_by_time": {},
                "worker": worker,
                "booking_worker_key": _booking_worker_match_key(row),
                "warehouse": warehouse,
            },
        )
        shift_time = _normalize_time(row.get(time_column))
        group["times"].append(shift_time)
        if shift_time and shift_time not in group["records_by_time"]:
            group["records_by_time"][shift_time] = row.to_dict()

    return groups


def _group_giriton_availability(df: pd.DataFrame) -> dict[tuple[str, str], list[str]]:
    if df.empty or "start_time" not in df.columns:
        return {}

    groups: dict[tuple[str, str], list[str]] = {}
    for _, row in df.iterrows():
        start = _normalize_time(row.get("start_time"))
        if not start or not _is_available_giriton_shift(row):
            continue

        key = (
            _clean(row.get("work_date")),
            _warehouse_match_key(row.get("warehouse")),
        )
        groups.setdefault(key, []).append(start)

    return groups


def _group_giriton_bookings(df: pd.DataFrame) -> dict[tuple[str, str, str], list[str]]:
    if df.empty or "start_time" not in df.columns:
        return {}

    groups: dict[tuple[str, str, str], list[str]] = {}
    for _, row in df.iterrows():
        start = _normalize_time(row.get("start_time"))
        worker_key = _booking_worker_match_key(row)
        if not start or not worker_key or not _is_booked_giriton_shift(row):
            continue

        key = (
            _clean(row.get("work_date")),
            worker_key,
            _warehouse_match_key(row.get("warehouse")),
        )
        groups.setdefault(key, []).append(start)

    return groups


def _format_diff(diff: int | None) -> str:
    if diff is None:
        return "-"
    if diff == 0:
        return "0 perc"
    return f"{diff:+d} perc"


def _nearest_giriton_times(
    muszakpro_times: list[str],
    giriton_times: list[str],
    tolerance_minutes: int,
) -> tuple[list[str], list[int], str]:
    if not muszakpro_times or not giriton_times:
        return [], [], "none"

    muszakpro_times = sorted(
        {_normalize_time(value) for value in muszakpro_times if _normalize_time(value)},
        key=lambda value: _time_minutes(value) or 0,
    )
    giriton_times = sorted(
        {_normalize_time(value) for value in giriton_times if _normalize_time(value)},
        key=lambda value: _time_minutes(value) or 0,
    )
    if len(giriton_times) < len(muszakpro_times):
        return [], [], "none"

    best: tuple[int, list[str], list[int], int] | None = None
    for candidate in giriton_times:
        first_diff = _diff_minutes(muszakpro_times[0], candidate)
        if first_diff is None or abs(first_diff) > tolerance_minutes:
            continue

        candidates_by_shift: list[list[tuple[str, int, int]]] = []
        for index, muszakpro_time in enumerate(muszakpro_times):
            target_minutes = (_time_minutes(muszakpro_time) or 0) + first_diff
            target_minutes %= 1440
            target_text = f"{target_minutes // 60:02d}:{target_minutes % 60:02d}"
            shift_candidates = []

            for giriton_time in giriton_times:
                target_diff = _diff_minutes(target_text, giriton_time)
                current_diff = _diff_minutes(muszakpro_time, giriton_time)
                if (
                    target_diff is None
                    or current_diff is None
                    or abs(target_diff) > tolerance_minutes
                ):
                    continue

                shift_candidates.append(
                    (
                        giriton_time,
                        current_diff,
                        abs(current_diff) + abs(target_diff) + abs(current_diff - first_diff),
                    )
                )

            if not shift_candidates:
                candidates_by_shift = []
                break

            candidates_by_shift.append(
                sorted(
                    shift_candidates,
                    key=lambda item: (item[2], _time_minutes(item[0]) or 0, index),
                )
            )

        if not candidates_by_shift:
            continue

        def choose(index: int, selected: list[str], diffs: list[int], score: int):
            nonlocal best
            if index == len(candidates_by_shift):
                if not _shift_gap_ok(selected):
                    return
                total_score = score + sum(abs(diff - first_diff) for diff in diffs) * 3
                if best is None or total_score < best[0]:
                    best = (total_score, selected[:], diffs[:], first_diff)
                return

            for giriton_time, current_diff, candidate_score in candidates_by_shift[index]:
                if giriton_time in selected:
                    continue
                next_selected = selected + [giriton_time]
                if not _shift_gap_ok(next_selected):
                    continue
                choose(index + 1, next_selected, diffs + [current_diff], score + candidate_score)

        choose(0, [], [], 0)

    if best is None:
        return [], [], "none"

    status = "exact" if all(diff == 0 for diff in best[2]) else "alternative"
    return best[1], best[2], status


def _nearest_single_giriton_time(
    muszakpro_time: str,
    giriton_times: list[str],
    tolerance_minutes: int,
) -> tuple[str, int | None, str]:
    if not muszakpro_time or not giriton_times:
        return "nincs találat", None, "none"

    best_time = ""
    best_diff = None
    for giriton_time in giriton_times:
        diff = _diff_minutes(muszakpro_time, giriton_time)
        if diff is None or abs(diff) > tolerance_minutes:
            continue
        if best_diff is None or abs(diff) < abs(best_diff):
            best_time = giriton_time
            best_diff = diff

    if best_diff is None:
        return "nincs találat", None, "none"

    status = "exact" if best_diff == 0 else "alternative"
    return best_time, best_diff, status


def _plan_giriton_day(
    muszakpro_times: list[str],
    available_times: list[str],
    booked_times: list[str],
    tolerance_minutes: int,
) -> dict[str, tuple[str, int, str]]:
    muszakpro_times = sorted(
        {_normalize_time(value) for value in muszakpro_times if _normalize_time(value)},
        key=lambda value: _time_minutes(value) or 0,
    )
    available_times = sorted(
        {_normalize_time(value) for value in available_times if _normalize_time(value)},
        key=lambda value: _time_minutes(value) or 0,
    )
    booked_times = sorted(
        {_normalize_time(value) for value in booked_times if _normalize_time(value)},
        key=lambda value: _time_minutes(value) or 0,
    )
    if not muszakpro_times:
        return {}

    best: tuple[int, list[tuple[str, str, int, str]]] | None = None
    candidates_by_shift: list[list[tuple[str, int, str, int]]] = []

    for muszakpro_time in muszakpro_times:
        booked_candidates = []
        for booked_time in booked_times:
            diff = _diff_minutes(muszakpro_time, booked_time)
            if diff is None or abs(diff) > tolerance_minutes:
                continue
            booked_candidates.append((booked_time, diff, "booked", abs(diff)))
        if booked_candidates:
            candidates_by_shift.append(
                sorted(
                    booked_candidates,
                    key=lambda item: (item[3], _time_minutes(item[0]) or 0),
                )
            )
            continue

        shift_candidates = []
        for giriton_time in available_times:
            diff = _diff_minutes(muszakpro_time, giriton_time)
            if diff is None or abs(diff) > tolerance_minutes:
                continue
            state = "exact" if diff == 0 else "alternative"
            shift_candidates.append((giriton_time, diff, state, abs(diff)))

        if not shift_candidates:
            return {}

        candidates_by_shift.append(
            sorted(
                shift_candidates,
                key=lambda item: (item[3], _time_minutes(item[0]) or 0),
            )
        )

    def choose(index: int, selected: list[tuple[str, str, int, str]], score: int):
        nonlocal best
        if index == len(candidates_by_shift):
            selected_times = [item[1] for item in selected]
            if not _shift_gap_ok(selected_times):
                return
            if best is None or score < best[0]:
                best = (score, selected[:])
            return

        muszakpro_time = muszakpro_times[index]
        used_available = {
            item[1]
            for item in selected
            if item[3] != "booked"
        }
        for giriton_time, diff, state, candidate_score in candidates_by_shift[index]:
            if state != "booked" and giriton_time in used_available:
                continue
            next_selected = selected + [(muszakpro_time, giriton_time, diff, state)]
            if not _shift_gap_ok([item[1] for item in next_selected]):
                continue
            choose(index + 1, next_selected, score + candidate_score)

    choose(0, [], 0)
    if best is None:
        return {}

    return {
        muszakpro_time: (giriton_time, diff, state)
        for muszakpro_time, giriton_time, diff, state in best[1]
    }


def _build_summary_rows(
    muszakpro_df: pd.DataFrame,
    giriton_df: pd.DataFrame,
    tolerance_minutes: int,
) -> pd.DataFrame:
    muszakpro_groups = _group_shifts(muszakpro_df, "shift_start")
    giriton_groups = _group_giriton_availability(giriton_df)
    booked_giriton_groups = _group_giriton_bookings(giriton_df)

    keys = sorted(
        set(muszakpro_groups),
        key=lambda key: (
            key[0],
            muszakpro_groups[key].get("worker", ""),
            muszakpro_groups[key].get("warehouse", ""),
        ),
    )
    rows = []

    for work_date, worker_key, warehouse_key in keys:
        muszakpro_group = muszakpro_groups.get((work_date, worker_key, warehouse_key), {})
        worker = muszakpro_group.get("worker", worker_key)
        booking_worker_key = muszakpro_group.get("booking_worker_key", "")
        warehouse = muszakpro_group.get("warehouse", "")
        muszakpro_values = sorted(
            [
                _normalize_time(value)
                for value in muszakpro_group.get("times", [])
                if _normalize_time(value)
            ],
            key=lambda value: _time_minutes(value) or 0,
        )
        giriton_source = giriton_groups.get((work_date, warehouse_key), [])
        giriton_values = sorted(
            [
                _normalize_time(value)
                for value in giriton_source
                if _normalize_time(value)
            ],
            key=lambda value: _time_minutes(value) or 0,
        )
        booked_values = sorted(
            [
                _normalize_time(value)
                for value in (
                    booked_giriton_groups.get((work_date, booking_worker_key, warehouse_key), [])
                    if booking_worker_key
                    else []
                )
                if _normalize_time(value)
            ],
            key=lambda value: _time_minutes(value) or 0,
        )
        daily_plan = _plan_giriton_day(
            muszakpro_values,
            giriton_values,
            booked_values,
            tolerance_minutes,
        )
        records_by_time = muszakpro_group.get("records_by_time", {})

        for muszakpro_time in muszakpro_values:
            source_record = records_by_time.get(muszakpro_time, {})
            giriton_booking = "-"
            giriton_offer = "-"
            if muszakpro_time in daily_plan:
                giriton_time, diff_value, plan_status = daily_plan[muszakpro_time]
                if plan_status == "booked":
                    status = "Lefoglalva"
                    giriton_state = "Lefoglalva"
                    giriton_booking = giriton_time
                    reason = "Ez a műszak már le van foglalva Giritonban"
                elif diff_value == 0:
                    status = "Egyezés"
                    giriton_state = "Nincs lefoglalva"
                    giriton_offer = giriton_time
                    reason = f"Pontos egyezés, napi 4:30 szabály ellenőrizve"
                else:
                    status = "Alternatíva"
                    giriton_state = "Nincs lefoglalva"
                    giriton_offer = giriton_time
                    reason = f"Napi újratervezés a tűrésen belül, 4:30 szabállyal"
            else:
                if len(muszakpro_values) == 1:
                    giriton_time, diff_value, single_status = _nearest_single_giriton_time(
                        muszakpro_time,
                        giriton_values,
                        tolerance_minutes,
                    )
                    if single_status == "exact":
                        status = "Egyezés"
                        giriton_state = "Nincs lefoglalva"
                        giriton_offer = giriton_time
                        reason = "Pontos egyezés"
                    elif single_status == "alternative":
                        status = "Alternatíva"
                        giriton_state = "Nincs lefoglalva"
                        giriton_offer = giriton_time
                        reason = "Egyedi alternatíva a tűrésen belül"
                    else:
                        status = "Sikertelen"
                        giriton_state = "-"
                        giriton_offer = giriton_time
                        reason = f"Nincs azonos raktáras szabad Giriton találat ±{tolerance_minutes} percen belül"
                else:
                    diff_value = None
                    status = "Sikertelen"
                    giriton_state = "-"
                    giriton_offer = "nincs érvényes napi terv"
                    reason = f"Nincs azonos raktáras napi Giriton lánc, ahol minden műszak között legalább 4:30 óra van"

            rows.append(
                {
                    "Dátum": work_date,
                    "Dolgozó": worker,
                    "Raktár": warehouse,
                    "MűszakPro": muszakpro_time,
                    "Giriton foglalás": giriton_booking,
                    "Giriton ajánlat": giriton_offer,
                    "Giriton állapot": giriton_state,
                    "Eltérés": _format_diff(diff_value),
                    "Állapot": status,
                    "Ok": reason,
                    "Serial": _clean(source_record.get("serial")),
                    "Courier ID": _clean(source_record.get("courier_id")),
                    "E-mail": _clean(source_record.get("email")).casefold(),
                }
            )

    return pd.DataFrame(rows)


def _render_html_table(df: pd.DataFrame, columns: list[str], empty_text: str) -> None:
    if df.empty:
        st.info(empty_text)
        return

    head = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body = []
    for _, source_row in df.iterrows():
        row = source_row.to_dict()
        cells = []
        for column in columns:
            value = row.get(column, "")
            class_name = _cell_class(row, column)
            class_attr = f" class='{class_name}'" if class_name else ""
            if column == "Állapot":
                cells.append(f"<td{class_attr}>{_status_badge(_clean(value))}</td>")
            elif column == "Giriton állapot":
                cells.append(f"<td{class_attr}>{_giriton_state_badge(_clean(value))}</td>")
            elif column == "Következő lépés":
                cells.append(f"<td{class_attr}>{_booking_action_badge(row)}</td>")
            else:
                cells.append(f"<td{class_attr}>{escape(_clean(value))}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")

    st.markdown(
        f"""
        <div class="table-wrap">
            <table class="styled-table">
                <thead><tr>{head}</tr></thead>
                <tbody>{''.join(body)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _format_frame(df: pd.DataFrame, columns: list[str], labels: dict[str, str]) -> pd.DataFrame:
    visible_columns = [column for column in columns if column in df.columns]
    if not visible_columns:
        return pd.DataFrame()

    return df[visible_columns].rename(columns=labels)


def _display_table(df: pd.DataFrame, columns: list[str], labels: dict[str, str], empty_text: str) -> None:
    table = _format_frame(df, columns, labels)
    if table.empty:
        st.info(empty_text)
        return

    st.dataframe(table, width="stretch", hide_index=True)


def _muszakpro_columns() -> tuple[list[str], dict[str, str]]:
    return (
        [
            "work_date",
            "courier_name",
            "warehouse",
            "shift_text",
            "shift_start",
            "booking_code",
            "serial",
            "fetched_at",
        ],
        {
            "work_date": "Dátum",
            "courier_name": "Dolgozó",
            "warehouse": "Raktár",
            "shift_text": "MűszakPro műszak",
            "shift_start": "Kezdés",
            "booking_code": "Kód",
            "serial": "Sorszám",
            "fetched_at": "Frissítve",
        },
    )


def _giriton_columns() -> tuple[list[str], dict[str, str]]:
    return (
        [
            "work_date",
            "courier_name",
            "warehouse",
            "start_time",
            "end_time",
            "occupancy",
            "booked",
            "maximum",
            "status",
            "serial",
            "fetched_at",
        ],
        {
            "work_date": "Dátum",
            "courier_name": "Dolgozó",
            "warehouse": "Raktár",
            "start_time": "Kezdés",
            "end_time": "Vége",
            "occupancy": "Foglaltság",
            "booked": "Foglalt",
            "maximum": "Maximum",
            "status": "Státusz",
            "serial": "Sorszám",
            "fetched_at": "Frissítve",
        },
    )


def _apply_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f7f9fb; color: #151f2f; }
        [data-testid="stSidebar"] {
            background: #f1f6f8;
            border-right: 1px solid #dce5ea;
        }
        .block-container { padding-top: 1.2rem; max-width: 1500px; }
        h1, h2, h3 { letter-spacing: 0; }
        div[data-testid="stButton"] button {
            border-radius: 7px;
            min-height: 42px;
            font-weight: 700;
        }
        .source-status {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin: 10px 0 18px;
        }
        .source-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            background: #ffffff;
            color: #344257;
            padding: 8px 11px;
            font-size: 0.9rem;
        }
        .source-chip strong { color: #172033; }
        .kpi {
            min-height: 90px;
            padding: 16px 18px;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            background: white;
            box-shadow: 0 1px 2px rgba(18, 38, 63, 0.04);
            display: grid;
            grid-template-columns: 48px 1fr;
            align-items: center;
            gap: 14px;
        }
        .kpi-label { color: #536173; font-size: 0.95rem; margin-bottom: 8px; }
        .kpi-value { font-size: 2rem; font-weight: 760; color: #1d66c1; }
        .kpi-green .kpi-value { color: #18834b; }
        .kpi-red .kpi-value { color: #c42b2b; }
        .kpi-amber .kpi-value { color: #c27605; }
        .kpi-icon {
            width: 46px;
            height: 46px;
            border-radius: 12px;
            background: #e9f5ff;
            color: #1d66c1;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 1.15rem;
        }
        .kpi-green .kpi-icon { background: #e9f8ef; color: #18834b; }
        .kpi-red .kpi-icon { background: #fff0f0; color: #c42b2b; }
        .kpi-amber .kpi-icon { background: #fff5df; color: #c27605; }
        .section-card {
            background: white;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            padding: 16px 18px;
            box-shadow: 0 1px 2px rgba(18, 38, 63, 0.04);
            margin-bottom: 12px;
        }
        .section-title {
            font-size: 1.12rem;
            font-weight: 760;
            color: #172033;
            margin-bottom: 2px;
        }
        .section-subtitle {
            color: #64748b;
            font-size: 0.9rem;
            margin-bottom: 10px;
        }
        .hero-panel {
            background: white;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            padding: 18px 20px;
            margin: 16px 0 14px;
        }
        .hero-head {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: flex-start;
            margin-bottom: 16px;
        }
        .hero-title {
            font-size: 1.35rem;
            font-weight: 780;
            color: #172033;
            margin-bottom: 4px;
        }
        .hero-note { color: #64748b; }
        .status-live {
            border: 1px solid #bee6c8;
            background: #f1fbf4;
            color: #18834b;
            border-radius: 8px;
            padding: 9px 14px;
            font-weight: 760;
            white-space: nowrap;
        }
        .progress-shell {
            height: 16px;
            border-radius: 999px;
            background: #edf2f5;
            overflow: hidden;
            margin-top: 10px;
        }
        .progress-fill {
            height: 100%;
            background: #0796a3;
            color: white;
            text-align: center;
            line-height: 16px;
            font-size: 0.78rem;
            font-weight: 700;
        }
        .layout-grid {
            display: grid;
            grid-template-columns: minmax(0, 1fr) 292px;
            gap: 16px;
            align-items: start;
        }
        .side-panel {
            background: white;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            padding: 16px 14px;
        }
        .side-panel h3 { margin-top: 0; }
        .summary-row {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            border-bottom: 1px solid #edf2f5;
            padding: 10px 0;
        }
        .summary-row:last-child { border-bottom: 0; }
        .side-action {
            display: block;
            text-align: center;
            margin-top: 12px;
            border: 1px solid #0796a3;
            border-radius: 7px;
            padding: 12px;
            font-weight: 760;
            color: #057783;
            background: #f0fbfc;
        }
        .side-action.primary {
            background: #0796a3;
            color: white;
        }
        .table-wrap {
            width: 100%;
            max-width: 100%;
            max-height: 62vh;
            overflow: auto;
            border: 1px solid #dce5ea;
            border-radius: 8px;
            background: white;
        }
        .styled-table {
            width: max-content;
            min-width: 1280px;
            border-collapse: collapse;
            font-size: 0.92rem;
        }
        .styled-table thead th {
            position: sticky;
            top: 0;
            z-index: 2;
        }
        .styled-table th,
        .styled-table td {
            padding: 12px 13px;
            border-bottom: 1px solid #e7edf1;
            text-align: left;
            white-space: nowrap;
        }
        .styled-table th {
            background: #f6f8fa;
            color: #243044;
            font-weight: 760;
        }
        .styled-table tr:last-child td { border-bottom: 0; }
        .styled-table td.match-ok {
            background: #e9f8ef;
            color: #13783e;
            border: 1px solid #8fd6a7;
            font-weight: 800;
        }
        .styled-table td.booked-ok {
            background: #eaf2ff;
            color: #155fc1;
            border: 1px solid #9bc0ff;
            font-weight: 800;
        }
        .styled-table td.booked-conflict {
            background: #fff7f7;
            color: #c42b2b;
            border: 2px solid #ff7b7b;
            font-weight: 850;
        }
        .status-badge,
        .action-badge {
            display: inline-block;
            min-width: 86px;
            border-radius: 7px;
            padding: 5px 10px;
            text-align: center;
            font-weight: 760;
            border: 1px solid #dce5ea;
        }
        .action-link,
        .action-link:visited {
            text-decoration: none;
        }
        .action-link:hover {
            filter: brightness(0.96);
        }
        .action-badge.disabled {
            background: #eef2f6;
            color: #64748b;
            border-color: #cbd5e1;
            cursor: not-allowed;
        }
        .status-badge.ok,
        .action-badge.ok { background: #e9f8ef; color: #18834b; border-color: #a9dfb8; }
        .status-badge.warn,
        .action-badge.warn { background: #fff5df; color: #b66a00; border-color: #efc96e; }
        .status-badge.bad,
        .action-badge.bad { background: #fff0f0; color: #c42b2b; border-color: #ffaaaa; }
        .status-badge.booked,
        .action-badge.booked { background: #eaf2ff; color: #155fc1; border-color: #9bc0ff; }
        @media (max-width: 1120px) {
            .layout-grid { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_kpi(label: str, value: int, tone: str = "blue", icon: str = "") -> None:
    st.markdown(
        f"""
        <div class="kpi kpi-{tone}">
            <div class="kpi-icon">{escape(icon or label[:1])}</div>
            <div>
                <div class="kpi-label">{escape(label)}</div>
                <div class="kpi-value">{value}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, ttl=300)
def _load_next_5_days():
    return pd.DataFrame(read_next_5_day_shift_comparison(limit=20000))


@st.cache_data(show_spinner=False, ttl=300)
def _load_muszakpro_data(start_date: date, end_date: date):
    return read_foglalasok_raw(
        start_date=start_date,
        end_date=end_date,
        limit=20000,
    )


@st.cache_data(show_spinner=False, ttl=300)
def _load_giriton_data(start_date: date, end_date: date):
    return read_giriton_shifts_raw(
        start_date=start_date,
        end_date=end_date,
        limit=20000,
    )


@st.cache_data(show_spinner=False, ttl=300)
def _load_latest_giriton_data():
    return read_giriton_shifts_raw(limit=1)


@st.cache_data(show_spinner=False, ttl=300)
def _load_giriton_day(work_date):
    return read_giriton_shifts_raw(
        start_date=work_date,
        end_date=work_date,
        limit=20000,
    )


@st.cache_data(show_spinner=False, ttl=300)
def _load_log_data(start_date: date, end_date: date):
    return read_giriton_booking_log(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        limit=1000,
    )


def _safe_load(label: str, loader, *args) -> tuple[pd.DataFrame, str]:
    try:
        data = loader(*args)
        return pd.DataFrame(data), ""
    except Exception as exc:
        return pd.DataFrame(), f"{label}: {exc}"


def _sidebar() -> tuple[str, date, date, time, time, int]:
    st.sidebar.title("foglalas.py")
    view = st.sidebar.radio(
        "Nézet",
        ["Összes", "Dolgozónként", "Sikertelenek", "Napló"],
        index=0,
        key="foglalas_view",
    )
    st.sidebar.divider()
    today = date.today()
    quick_col_1, quick_col_2 = st.sidebar.columns(2)
    if quick_col_1.button("Ma", width="stretch"):
        st.session_state["foglalas_start_date"] = today
        st.session_state["foglalas_end_date"] = today
        st.rerun()
    if quick_col_2.button("Holnap", width="stretch"):
        tomorrow = today + timedelta(days=1)
        st.session_state["foglalas_start_date"] = tomorrow
        st.session_state["foglalas_end_date"] = tomorrow
        st.rerun()
    if st.sidebar.button("Következő 5 nap", width="stretch"):
        st.session_state["foglalas_start_date"] = today
        st.session_state["foglalas_end_date"] = today + timedelta(days=4)
        st.rerun()
    start_date = st.sidebar.date_input(
        "Kezdő dátum",
        value=today,
        key="foglalas_start_date",
    )
    end_date = st.sidebar.date_input(
        "Záró dátum",
        value=today + timedelta(days=5),
        key="foglalas_end_date",
    )
    st.sidebar.write("Időtartomány")
    start_col, end_col = st.sidebar.columns(2)
    start_time = start_col.time_input(
        "Kezdete",
        value=time(0, 0),
        step=900,
        key="foglalas_start_time",
    )
    end_time = end_col.time_input(
        "Vége",
        value=time(23, 59),
        step=900,
        key="foglalas_end_time",
    )
    st.sidebar.write("Források")
    st.sidebar.toggle("MűszakPro", value=True, disabled=True)
    st.sidebar.toggle("Giriton", value=True, disabled=True)
    st.sidebar.write("Eltérés: ±30 perc")
    tolerance_minutes = st.sidebar.slider(
        "Tűrés",
        min_value=5,
        max_value=120,
        value=30,
        step=5,
        label_visibility="collapsed",
        key="foglalas_tolerance",
    )
    st.sidebar.caption("Napi terv szabály: két Giriton műszak között minimum 4:30 óra kell.")
    st.sidebar.write("Foglalási állapot")
    for status in ["Egyezés", "Alternatíva", "Sikertelen", "Lefoglalva"]:
        st.sidebar.checkbox(
            status,
            value=True,
            key=f"foglalas_status_{status}",
        )
    st.sidebar.divider()
    st.sidebar.write("Kézi robotindítás")
    if st.sidebar.button("Giriton futtatása kézzel", width="stretch"):
        if end_date < start_date:
            st.sidebar.error("A Giriton futtatáshoz a záró dátum nem lehet korábbi.")
        else:
            days_to_sync = max((end_date - start_date).days + 1, 1)
            try:
                result = _dispatch_workflow_fallback(
                    "giriton-raw-export.yml",
                    {
                        "start_date": start_date.isoformat(),
                        "days": str(days_to_sync),
                    },
                )
                st.session_state["foglalas_last_giriton_raw_dispatch"] = result
                st.sidebar.success(
                    f"Giriton kézi futás indítva: {start_date} + {days_to_sync} nap"
                )
            except GitHubActionsError as exc:
                st.sidebar.error(str(exc))
            except Exception as exc:
                st.sidebar.error(f"Giriton kézi indítás hiba: {exc}")

    if st.sidebar.button("Adatok újraolvasása DB-ből", width="stretch"):
        st.cache_data.clear()
        st.rerun()

    return view, start_date, end_date, start_time, end_time, int(tolerance_minutes)


def _render_source_tables(muszakpro_df: pd.DataFrame, giriton_df: pd.DataFrame) -> None:
    muszakpro_columns, muszakpro_labels = _muszakpro_columns()
    giriton_columns, giriton_labels = _giriton_columns()

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(
            """
            <div class="section-card">
                <div class="section-title">MűszakPro adatok</div>
                <div class="section-subtitle">A MűszakPro-ból érkezett foglalt műszakok</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _display_table(
            muszakpro_df,
            muszakpro_columns,
            muszakpro_labels,
            "Nincs MűszakPro adat ebben a szűrésben.",
        )

    with right:
        st.markdown(
            """
            <div class="section-card">
                <div class="section-title">Giriton adatok</div>
                <div class="section-subtitle">A Giriton rendszerből érkezett műszakok</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _display_table(
            giriton_df,
            giriton_columns,
            giriton_labels,
            "Nincs Giriton adat ebben a szűrésben.",
        )


def _booking_candidate_label(row: dict) -> str:
    return (
        f"{_clean(row.get('Dátum'))} | {_clean(row.get('Raktár'))} | "
        f"MP {_clean(row.get('MűszakPro'))} -> Giriton "
        f"{_clean(row.get('Giriton ajánlat')) or _clean(row.get('Giriton foglalás'))} | "
        f"{_clean(row.get('Dolgozó'))} | serial: {_clean(row.get('Serial')) or '-'}"
    )


def _dispatch_auto_booking(row: dict, dry_run: bool) -> None:
    serial = _clean(row.get("Serial"))
    work_date = _clean(row.get("Dátum"))
    if not serial:
        st.error("Ehhez a sorhoz nincs MűszakPro serial, ezért nem indítható célzott foglalás.")
        return
    if not work_date:
        st.error("Ehhez a sorhoz nincs dátum, ezért nem indítható foglalás.")
        return
    if not dry_run and serial in _started_booking_serials():
        st.warning("Erre a sorra már el lett indítva az éles foglalás, ezért nem indítok még egyet.")
        return

    workflow_inputs = {
        "start_date": work_date,
        "end_date": work_date,
        "serial": serial,
        "warehouse": _clean(row.get("Raktár")).upper(),
        "email": _clean(row.get("E-mail")).casefold(),
        "shift_start": _clean(row.get("MűszakPro")),
        "dry_run": "true" if dry_run else "false",
    }
    result = _dispatch_workflow_fallback(AUTO_BOOKING_WORKFLOW, workflow_inputs)
    if not dry_run:
        _mark_booking_started(serial)
    st.session_state["foglalas_last_github_dispatch"] = result
    mode = "ellenőrzés" if dry_run else "éles foglalás"
    st.success(
        f"Giriton {mode} indítva: {result['workflow']} / {result['ref']} / {result['triggered_at']}"
    )


def _query_param_value(name: str) -> str:
    try:
        value = st.query_params.get(name, "")
    except Exception:
        return ""
    if isinstance(value, list):
        return _clean(value[0] if value else "")
    return _clean(value)


def _matching_booking_row(summary_df: pd.DataFrame, identity: dict[str, str]) -> dict | None:
    if summary_df.empty:
        return None

    for _, row in summary_df.iterrows():
        row_dict = row.to_dict()
        row_identity = _booking_action_identity(row_dict)
        if row_identity != identity:
            continue
        if _clean(row_dict.get("Állapot")) != "Egyezés":
            return None
        if _clean(row_dict.get("Giriton állapot")) != "Nincs lefoglalva":
            return None
        return row_dict
    return None


def _query_booking_identity() -> dict[str, str]:
    return {
        "serial": _query_param_value("serial"),
        "work_date": _query_param_value("work_date"),
        "worker": _query_param_value("worker"),
        "warehouse": _query_param_value("warehouse").upper(),
        "shift_start": _query_param_value("shift_start"),
    }


def _handle_table_booking_action(summary_df: pd.DataFrame) -> None:
    if _query_param_value("foglalas_action") != "book_serial":
        return

    token = _query_param_value("action_token")
    actions = st.session_state.get("foglalas_booking_actions", {})
    token_identity = actions.pop(token, None) if token else None
    query_identity = _query_booking_identity()
    identity = token_identity or query_identity
    required_fields = ["serial", "work_date", "worker", "warehouse", "shift_start"]
    if any(not identity.get(field) for field in required_fields):
        st.error("A foglalás indításához hiányzik egy sorazonosító adat. Frissítsd az oldalt, és nyomd meg újra a konkrét sor gombját.")
        st.query_params.clear()
        return

    serial = identity["serial"]
    if serial in _started_booking_serials():
        st.warning("Erre a sorra már el lett indítva az éles foglalás, ezért nem indítok még egyet.")
        st.query_params.clear()
        return

    selected_row = _matching_booking_row(summary_df, identity)
    if selected_row is None:
        st.error(
            "Nem indítottam foglalást, mert a kattintott sor már nem egyezik a látható listával "
            "vagy nem foglalható állapotú."
        )
        st.query_params.clear()
        return

    try:
        _dispatch_auto_booking(selected_row, dry_run=False)
    except GitHubActionsError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Táblázatos foglalás indítás hiba: {exc}")
    finally:
        st.query_params.clear()


def _dispatch_bulk_warehouse_booking(
    *,
    start_date: str,
    end_date: str,
    warehouse: str,
    dry_run: bool,
) -> None:
    warehouse = _clean(warehouse).upper()
    if warehouse not in {"BUD1", "BUD2"}:
        st.error("Raktár szerinti tömeges indításhoz válassz BUD1 vagy BUD2 raktárat.")
        return

    result = _dispatch_workflow_fallback(
        AUTO_BOOKING_WORKFLOW,
        {
            "start_date": start_date,
            "end_date": end_date,
            "serial": "",
            "warehouse": warehouse,
            "dry_run": "true" if dry_run else "false",
        },
    )
    st.session_state["foglalas_last_github_dispatch"] = result
    mode = "ellenőrzés" if dry_run else "éles tömeges foglalás"
    st.success(
        f"{warehouse} raktár {mode} indítva: {result['workflow']} / {result['ref']} / {result['triggered_at']}"
    )


def _exact_booking_rows(summary_df: pd.DataFrame) -> pd.DataFrame:
    if summary_df.empty:
        return summary_df

    rows = summary_df[
        (summary_df["Állapot"] == "Egyezés")
        & (summary_df["Eltérés"] == "0 perc")
        & (summary_df["Giriton állapot"] == "Nincs lefoglalva")
        & (summary_df["Serial"].fillna("").astype(str).str.strip() != "")
    ].copy()
    if rows.empty:
        return rows

    started = _started_booking_serials()
    rows = rows[~rows["Serial"].astype(str).str.strip().isin(started)]
    return rows.drop_duplicates(subset=["Serial"])


def _dispatch_exact_bulk_bookings(rows: pd.DataFrame) -> None:
    if rows.empty:
        st.warning("Nincs indítható 100%-os egyezés ebben a szűrésben.")
        return

    dispatched = 0
    skipped = 0
    last_result = None
    for row in rows.to_dict("records"):
        serial = _clean(row.get("Serial"))
        work_date = _clean(row.get("Dátum"))
        if not serial or not work_date:
            skipped += 1
            continue
        if serial in _started_booking_serials():
            skipped += 1
            continue

        last_result = _dispatch_workflow_fallback(
            AUTO_BOOKING_WORKFLOW,
            {
                "start_date": work_date,
                "end_date": work_date,
                "serial": serial,
                "warehouse": _clean(row.get("Raktár")).upper(),
                "email": _clean(row.get("E-mail")).casefold(),
                "shift_start": _clean(row.get("MűszakPro")),
                "dry_run": "false",
            },
        )
        _mark_booking_started(serial)
        dispatched += 1

    if last_result:
        st.session_state["foglalas_last_github_dispatch"] = last_result

    if dispatched:
        st.success(
            f"{dispatched} db 100%-os egyezés éles foglalása elindítva "
            f"({dispatched} külön célzott GitHub robotfutás)."
        )
    if skipped:
        st.warning(f"{skipped} sor kimaradt, mert hiányzott adat vagy már el lett indítva.")


def _render_github_status_panel(key_prefix: str) -> None:
    st.markdown("### GitHub állapot")
    refresh_col, hint_col = st.columns([1, 2.4])
    if refresh_col.button(
        "GitHub állapot frissítése",
        width="stretch",
        key=f"{key_prefix}_github_refresh",
    ):
        st.session_state[f"{key_prefix}_github_status_refresh"] = (
            st.session_state.get(f"{key_prefix}_github_status_refresh", 0) + 1
        )

    last_dispatch = st.session_state.get("foglalas_last_github_dispatch")
    if last_dispatch:
        hint_col.success(
            f"Utolsó indítás: {last_dispatch.get('workflow')} / {last_dispatch.get('triggered_at')}"
        )
    else:
        hint_col.caption("Itt látszik majd a legutóbbi Giriton Auto Booking workflow állapota.")

    try:
        runs = _latest_auto_booking_runs(limit=5)
    except GitHubActionsError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"GitHub állapot lekérés hiba: {exc}")
        return

    if not runs:
        st.info("Még nincs látható Giriton Auto Booking futás.")
        return

    rows = []
    for run in runs:
        rows.append(
            {
                "Állapot": _github_status_label(run),
                "Indítva": _format_github_time(run.get("created_at")),
                "Frissítve": _format_github_time(run.get("updated_at")),
                "Branch": run.get("head_branch") or "-",
                "Link": run.get("html_url") or "",
            }
        )

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _render_individual_booking_panel(summary_df: pd.DataFrame, key_prefix: str) -> None:
    if summary_df.empty:
        st.info("Nincs kiválasztható sor az egyéni foglaláshoz.")
        return

    candidates = summary_df[
        summary_df["Állapot"].isin(["Egyezés", "Alternatíva"])
        & (summary_df["Giriton állapot"] == "Nincs lefoglalva")
    ].copy()
    if candidates.empty:
        st.info("Ebben a szűrésben nincs egyénileg indítható, még nem lefoglalt Giriton sor.")
        return

    rows = candidates.to_dict("records")
    options = {_booking_candidate_label(row): row for row in rows}
    selected_label = st.selectbox(
        "Egyéni foglalásra kiválasztott sor",
        list(options.keys()),
        key=f"{key_prefix}_single_booking_row",
    )
    selected_row = options[selected_label]

    info_cols = st.columns(4)
    info_cols[0].metric("Dátum", _clean(selected_row.get("Dátum")) or "-")
    info_cols[1].metric("Raktár", _clean(selected_row.get("Raktár")) or "-")
    info_cols[2].metric("MűszakPro", _clean(selected_row.get("MűszakPro")) or "-")
    info_cols[3].metric("Giriton ajánlat", _clean(selected_row.get("Giriton ajánlat")) or "-")

    action_col_1, action_col_2 = st.columns([1, 1.4])
    if action_col_1.button(
        "Ellenőrzés indítása",
        width="stretch",
        key=f"{key_prefix}_single_dry_run",
    ):
        try:
            _dispatch_auto_booking(selected_row, dry_run=True)
        except GitHubActionsError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Váratlan hiba az ellenőrzés indításánál: {exc}")

    live_enabled = action_col_2.checkbox(
        "Éles foglalás engedélyezése erre az egy sorra",
        key=f"{key_prefix}_single_live_enabled",
    )
    if live_enabled:
        st.warning(
            "Éles indítás csak a kiválasztott MűszakPro serialra megy, nem tömeges futás."
        )
        confirmation = st.text_input(
            "Megerősítés: írd be pontosan, hogy ELES",
            key=f"{key_prefix}_single_live_confirmation",
        )
        if st.button(
            "Kiválasztott sor foglalása",
            type="primary",
            width="stretch",
            key=f"{key_prefix}_single_live_run",
        ):
            if confirmation != "ELES":
                st.error("Éles indításhoz a megerősítő mezőbe ezt írd: ELES")
            else:
                try:
                    _dispatch_auto_booking(selected_row, dry_run=False)
                except GitHubActionsError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Váratlan hiba az éles foglalás indításánál: {exc}")

    _render_github_status_panel(key_prefix)


def _render_mass_view(summary_df: pd.DataFrame) -> None:
    if summary_df.empty:
        st.info("Nincs megjeleníthető egyeztetési sor ebben a szűrésben.")
        return

    exact_count = int((summary_df["Állapot"] == "Egyezés").sum())
    alternative_count = int((summary_df["Állapot"] == "Alternatíva").sum())
    failed_count = int((summary_df["Állapot"] == "Sikertelen").sum())
    booked_count = int((summary_df["Állapot"] == "Lefoglalva").sum())
    exact_ready = _exact_booking_rows(summary_df)
    target_count = max(len(summary_df), 1)
    progress = min(round((exact_count + booked_count) / target_count * 100), 100)

    st.markdown(
        f"""
        <div class="hero-panel">
            <div class="hero-head">
                <div>
                    <div class="hero-title">Tömeges foglalás</div>
                    <div class="hero-note">Egyező műszakok automatikus foglalása, problémás esetek külön listában</div>
                </div>
                <div class="status-live">Előkészítve</div>
            </div>
            <strong>Foglalható egyezések: {exact_count} / {len(summary_df)}</strong>
            <div class="progress-shell"><div class="progress-fill" style="width:{progress}%">{progress}%</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([4, 1.25], gap="large")
    with left:
        st.markdown("### Összesített foglalási lista")
        st.caption(f"Megjelenített sorok: {len(summary_df)}")
        table_df = summary_df.copy()
        table_df["Következő lépés"] = table_df["Állapot"]
        _render_html_table(
            table_df,
            [
                "Dátum",
                "Dolgozó",
                "Raktár",
                "MűszakPro",
                "Giriton foglalás",
                "Giriton ajánlat",
                "Giriton állapot",
                "Eltérés",
                "Állapot",
                "Következő lépés",
            ],
            "Nincs összesített sor.",
        )

        st.markdown("### Sikertelen foglalások")
        failed_df = summary_df[summary_df["Állapot"] == "Sikertelen"].copy()
        st.caption(f"Sikertelen sorok: {len(failed_df)}")
        if not failed_df.empty:
            failed_df["Következő lépés"] = failed_df["Állapot"]
        _render_html_table(
            failed_df,
            [
                "Dátum",
                "Dolgozó",
                "Raktár",
                "MűszakPro",
                "Giriton foglalás",
                "Giriton ajánlat",
                "Giriton állapot",
                "Eltérés",
                "Ok",
                "Következő lépés",
            ],
            "Nincs sikertelen sor.",
        )

    with right:
        st.markdown(
            f"""
            <div class="side-panel">
                <h3>Tömeges művelet</h3>
                <div class="summary-row"><span>Foglalható egyezések:</span><strong style="color:#18834b">{exact_count}</strong></div>
                <div class="summary-row"><span>Alternatívával foglalható:</span><strong style="color:#c27605">{alternative_count}</strong></div>
                <div class="summary-row"><span>Sikertelen:</span><strong style="color:#c42b2b">{failed_count}</strong></div>
                <div class="summary-row"><span>Lefoglalva:</span><strong style="color:#155fc1">{booked_count}</strong></div>
                <div class="section-subtitle" style="margin-top:14px;margin-bottom:0;">Raktár szerinti tömeges indítás</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("#### 100% egyezések")
        exact_dates = (
            sorted(exact_ready["Dátum"].dropna().astype(str).unique().tolist())
            if not exact_ready.empty and "Dátum" in exact_ready.columns
            else []
        )
        selected_exact_date = ""
        exact_ready_for_day = exact_ready
        if exact_dates:
            selected_exact_date = st.selectbox(
                "100%-os indítás napja",
                exact_dates,
                key="foglalas_exact_bulk_date",
            )
            exact_ready_for_day = exact_ready[
                exact_ready["Dátum"].astype(str) == selected_exact_date
            ]
        st.caption(
            f"Csak pontos, 0 perces, még nem lefoglalt sorok a kiválasztott napon: {len(exact_ready_for_day)}"
        )
        if not exact_ready_for_day.empty:
            preview = ", ".join(
                f"{_clean(row.get('Dolgozó'))} {_clean(row.get('MűszakPro'))}"
                for row in exact_ready_for_day.head(5).to_dict("records")
            )
            st.caption(preview)
        exact_live_enabled = st.checkbox(
            "Éles 100%-os egyezések indítása",
            key="foglalas_exact_bulk_live_enabled",
            disabled=exact_ready_for_day.empty,
        )
        if exact_live_enabled:
            expected_confirmation = f"ELES {selected_exact_date}"
            st.warning(
                f"Éles indítás: {selected_exact_date}, {len(exact_ready_for_day)} db pontos egyezés. "
                f"Ez {len(exact_ready_for_day)} külön célzott GitHub robotfutás lesz, serialonként egy. "
                "Alternatíva nem kerül bele."
            )
            exact_confirmation = st.text_input(
                f"Megerősítés: írd be pontosan, hogy {expected_confirmation}",
                key="foglalas_exact_bulk_live_confirmation",
            )
            if st.button(
                f"100% egyezések foglalása {selected_exact_date} ({len(exact_ready_for_day)})",
                type="primary",
                width="stretch",
                key="foglalas_exact_bulk_live_run",
            ):
                if exact_confirmation != expected_confirmation:
                    st.error(f"Éles indításhoz a megerősítő mezőbe ezt írd: {expected_confirmation}")
                else:
                    try:
                        _dispatch_exact_bulk_bookings(exact_ready_for_day)
                    except GitHubActionsError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"100%-os egyezések tömeges indítási hiba: {exc}")

        st.divider()
        warehouse_options = [
            value
            for value in ["BUD1", "BUD2"]
            if not summary_df[summary_df["Raktár"].astype(str).str.upper() == value].empty
        ] or ["BUD1", "BUD2"]
        selected_warehouse = st.selectbox(
            "Raktár",
            warehouse_options,
            key="foglalas_bulk_warehouse",
        )
        warehouse_df = summary_df[
            summary_df["Raktár"].astype(str).str.upper() == selected_warehouse
        ]
        warehouse_ready = warehouse_df[
            warehouse_df["Állapot"].isin(["Egyezés", "Alternatíva"])
            & (warehouse_df["Giriton állapot"] == "Nincs lefoglalva")
        ]
        st.caption(
            f"{selected_warehouse}: indítható sorok száma ebben a szűrésben: {len(warehouse_ready)}"
        )
        if st.button(
            "Foglalható sorok ellenőrzése",
            width="stretch",
            key="foglalas_bulk_warehouse_dry_run",
            disabled=warehouse_ready.empty,
        ):
            try:
                _dispatch_bulk_warehouse_booking(
                    start_date=str(summary_df["Dátum"].min()),
                    end_date=str(summary_df["Dátum"].max()),
                    warehouse=selected_warehouse,
                    dry_run=True,
                )
            except GitHubActionsError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Raktár ellenőrzés indítás hiba: {exc}")

        live_enabled = st.checkbox(
            "Éles raktár szerinti tömeges foglalás engedélyezése",
            key="foglalas_bulk_warehouse_live_enabled",
            disabled=warehouse_ready.empty,
        )
        if live_enabled:
            st.warning(
                f"Éles tömeges indítás: {selected_warehouse} raktár, {len(warehouse_ready)} indítható sor."
            )
            confirmation = st.text_input(
                "Megerősítés: írd be pontosan, hogy ELES",
                key="foglalas_bulk_warehouse_live_confirmation",
            )
            if st.button(
                "Raktár tömeges foglalása",
                type="primary",
                width="stretch",
                key="foglalas_bulk_warehouse_live_run",
            ):
                if confirmation != "ELES":
                    st.error("Éles raktárindításhoz a megerősítő mezőbe ezt írd: ELES")
                else:
                    try:
                        _dispatch_bulk_warehouse_booking(
                            start_date=str(summary_df["Dátum"].min()),
                            end_date=str(summary_df["Dátum"].max()),
                            warehouse=selected_warehouse,
                            dry_run=False,
                        )
                    except GitHubActionsError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Raktár tömeges foglalás indítás hiba: {exc}")

        st.markdown(
            """
            <div class="side-panel">
                <h3>DB alap</h3>
                <div class="summary-row"><span>raw_muszakpro_bookings</span><strong>MP</strong></div>
                <div class="summary-row"><span>giriton_shifts_raw</span><strong>G</strong></div>
                <div class="summary-row"><span>vw_courier_next_5_day_shifts</span><strong>5 nap</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_worker_view(
    summary_df: pd.DataFrame,
    muszakpro_df: pd.DataFrame,
    giriton_df: pd.DataFrame,
) -> None:
    workers = _worker_options(muszakpro_df, giriton_df)
    worker = st.selectbox("Dolgozó részletes nézete", workers)
    worker_summary = summary_df
    if worker != "Összes dolgozó" and not summary_df.empty:
        worker_summary = summary_df[summary_df["Dolgozó"] == worker]

    st.markdown("### Dolgozó foglalási listája")
    if not worker_summary.empty:
        worker_table = worker_summary.copy()
        worker_table["Következő lépés"] = worker_table["Állapot"]
    else:
        worker_table = worker_summary
    _render_html_table(
        worker_table,
        [
            "Dátum",
            "Dolgozó",
            "Raktár",
            "MűszakPro",
            "Giriton foglalás",
            "Giriton ajánlat",
            "Giriton állapot",
            "Eltérés",
            "Állapot",
            "Következő lépés",
        ],
        "Nincs foglalási sor ehhez a dolgozóhoz.",
    )

    st.markdown("### Egyéni foglalás")
    _render_individual_booking_panel(worker_summary, "worker")

    with st.expander("Nyers forrásadatok", expanded=False):
        _render_source_tables(
            _apply_worker(muszakpro_df, worker),
            _apply_worker(giriton_df, worker),
        )


def _render_differences(comparison_df: pd.DataFrame) -> None:
    if comparison_df.empty or "missing_source" not in comparison_df.columns:
        st.info("Nincs egyeztetési adat a következő 5 napra.")
        return

    has_missing = comparison_df["missing_source"].fillna("").astype(str).str.strip() != ""
    differences = comparison_df[has_missing]
    if differences.empty:
        st.success("A következő 5 nap egyeztetésében nincs eltérés.")
        return

    _display_table(
        differences,
        [
            "work_date",
            "courier_name",
            "warehouse",
            "shift_start",
            "shift_end",
            "giriton_status",
            "muszakpro_status",
            "missing_source",
            "updated_at",
        ],
        {
            "work_date": "Dátum",
            "courier_name": "Dolgozó",
            "warehouse": "Raktár",
            "shift_start": "Kezdés",
            "shift_end": "Vége",
            "giriton_status": "Giriton",
            "muszakpro_status": "MűszakPro",
            "missing_source": "Hiány",
            "updated_at": "Frissítve",
        },
        "Nincs eltérés ebben a szűrésben.",
    )


def _render_log(log_df: pd.DataFrame) -> None:
    if log_df.empty:
        st.info("Nincs napló ebben az időszakban.")
        return

    _display_table(
        log_df,
        [
            "created_at",
            "work_date",
            "courier_name",
            "warehouse",
            "shift_start",
            "status",
            "message",
            "serial",
        ],
        {
            "created_at": "Időpont",
            "work_date": "Dátum",
            "courier_name": "Dolgozó",
            "warehouse": "Raktár",
            "shift_start": "Kezdés",
            "status": "Státusz",
            "message": "Üzenet",
            "serial": "Sorszám",
        },
        "Nincs megjeleníthető napló.",
    )


def _render_recent_booking_issues(log_df: pd.DataFrame) -> None:
    if log_df.empty or "status" not in log_df.columns:
        return

    issue_statuses = {
        "SHIFT_NOT_EMPTY",
        "SHIFT_NOT_FOUND",
        "COURIER_NOT_SELECTED",
        "CHOOSE_BUTTON_NOT_FOUND",
        "COURIER_SELECTED_NOT_VERIFIED",
        "SELECTION_DIALOG_STILL_OPEN",
    }
    rows = log_df.copy()
    rows["status"] = rows["status"].fillna("").astype(str)
    issues = rows[rows["status"].isin(issue_statuses)].copy()
    if issues.empty:
        return

    if "created_at" in issues.columns:
        issues = issues.sort_values("created_at", ascending=False)

    latest = issues.head(5)
    with st.expander("Legutóbbi robot hibák / figyelmeztetések", expanded=True):
        st.caption("Itt látszik, ha a robot nem foglalt, és miért állt meg.")
        _display_table(
            latest,
            [
                "created_at",
                "work_date",
                "courier_name",
                "warehouse",
                "shift_start",
                "status",
                "message",
            ],
            {
                "created_at": "Időpont",
                "work_date": "Dátum",
                "courier_name": "Dolgozó",
                "warehouse": "Raktár",
                "shift_start": "Kezdés",
                "status": "Ok",
                "message": "Részlet",
            },
            "Nincs robot hiba.",
        )


def show_foglalas_streamlit_page() -> None:
    _apply_styles()
    view, start_date, end_date, start_time, end_time, tolerance_minutes = _sidebar()

    if end_date < start_date:
        st.error("A záró dátum nem lehet korábbi, mint a kezdő dátum.")
        return

    comparison_df, comparison_error = _safe_load("Egyeztetés", _load_next_5_days)
    muszakpro_df, muszakpro_error = _safe_load(
        "MűszakPro",
        _load_muszakpro_data,
        start_date,
        end_date,
    )
    giriton_df, giriton_error = _safe_load(
        "Giriton",
        _load_giriton_data,
        start_date,
        end_date,
    )
    latest_giriton_df, latest_giriton_error = _safe_load(
        "Giriton legfrissebb sor",
        _load_latest_giriton_data,
    )
    log_df, log_error = _safe_load("Napló", _load_log_data, start_date, end_date)

    if not muszakpro_df.empty:
        muszakpro_df = muszakpro_df.copy()
        muszakpro_df["shift_start"] = muszakpro_df.get(
            "shift_text",
            pd.Series(dtype=str),
        ).map(_shift_start)

    comparison_df = _filter_time(comparison_df, "shift_start", start_time, end_time)
    muszakpro_df = _filter_time(muszakpro_df, "shift_start", start_time, end_time)
    giriton_df = _filter_time(giriton_df, "start_time", start_time, end_time)
    summary_df = _build_summary_rows(muszakpro_df, giriton_df, tolerance_minutes)
    selected_statuses = [
        status
        for status in ["Egyezés", "Alternatíva", "Sikertelen", "Lefoglalva"]
        if st.session_state.get(f"foglalas_status_{status}", True)
    ]
    if selected_statuses and not summary_df.empty:
        summary_df = summary_df[summary_df["Állapot"].isin(selected_statuses)]

    st.title("foglalas.py")
    st.caption(
        f"Szűrt időszak: {start_date} - {end_date}, "
        f"{start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}. "
        "MűszakPro és Giriton egyeztetés. Éles foglalás még nincs bekötve."
    )
    selected_label = (
        start_date.strftime("%Y.%m.%d.")
        if start_date == end_date
        else f"{start_date.strftime('%Y.%m.%d.')} - {end_date.strftime('%Y.%m.%d.')}"
    )
    st.markdown(
        f"""
        <div class="source-chip">
            <strong>Kiválasztott nap/időszak</strong>
            {selected_label} · {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="source-status">
            <div class="source-chip"><strong>MűszakPro</strong> utolsó frissítés: {_latest(muszakpro_df, "fetched_at")}</div>
            <div class="source-chip"><strong>Giriton</strong> utolsó frissítés: {_latest(giriton_df if not giriton_df.empty else latest_giriton_df, "fetched_at")}</div>
            <div class="source-chip"><strong>Egyeztetés</strong> frissítve: {_latest(comparison_df, "updated_at")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    errors = [
        error
        for error in [
            comparison_error,
            muszakpro_error,
            giriton_error,
            latest_giriton_error,
            log_error,
        ]
        if error
    ]
    if errors:
        st.warning("Nem minden DB olvasás sikerült: " + " | ".join(errors))

    _handle_table_booking_action(summary_df)
    _render_recent_booking_issues(log_df)

    workers_count = (
        len(set(summary_df["Dolgozó"].dropna().astype(str)))
        if not summary_df.empty and "Dolgozó" in summary_df.columns
        else 0
    )
    muszakpro_count = len(muszakpro_df)
    giriton_count = len(giriton_df)
    exact_count = int((summary_df["Állapot"] == "Egyezés").sum()) if not summary_df.empty else 0
    failed_count = int((summary_df["Állapot"] == "Sikertelen").sum()) if not summary_df.empty else 0
    alternative_count = int((summary_df["Állapot"] == "Alternatíva").sum()) if not summary_df.empty else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        _render_kpi("Dolgozók", workers_count, "blue", "D")
    with c2:
        _render_kpi("MűszakPro sor", muszakpro_count, "blue", "MP")
    with c3:
        _render_kpi("Giriton sor", giriton_count, "blue", "G")
    with c4:
        _render_kpi("Egyezés", exact_count, "green", "OK")
    with c5:
        _render_kpi("Figyelendő", failed_count + alternative_count, "red", "!")

    st.write("")
    if view == "Összes":
        _render_mass_view(summary_df)
    elif view == "Dolgozónként":
        _render_worker_view(summary_df, muszakpro_df, giriton_df)
    elif view == "Sikertelenek":
        failed_only = summary_df[summary_df["Állapot"] == "Sikertelen"] if not summary_df.empty else summary_df
        if not failed_only.empty:
            failed_only = failed_only.copy()
            failed_only["Következő lépés"] = failed_only["Állapot"]
        _render_html_table(
            failed_only,
            [
                "Dátum",
                "Dolgozó",
                "Raktár",
                "MűszakPro",
                "Giriton foglalás",
                "Giriton ajánlat",
                "Giriton állapot",
                "Eltérés",
                "Ok",
                "Következő lépés",
            ],
            "Nincs sikertelen sor.",
        )
    else:
        _render_log(log_df)


if __name__ == "__main__":
    show_foglalas_streamlit_page()
