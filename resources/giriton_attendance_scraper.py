import re
import time

from robot.libraries.BuiltIn import BuiltIn

try:
    from resources.giriton_attendance_uidl import (
        parse_attendance_uidl_rows,
        split_courier_text,
    )
except ModuleNotFoundError:
    from giriton_attendance_uidl import (
        parse_attendance_uidl_rows,
        split_courier_text,
    )


def _selenium():
    return BuiltIn().get_library_instance("SeleniumLibrary")


def _driver():
    return _selenium().driver


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _reverse_name(name):
    parts = _clean(name).split(maxsplit=1)

    if len(parts) != 2:
        return _clean(name)

    return f"{parts[1]} {parts[0]}"


def _is_clock_time(value):
    text = _clean(value)
    match = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text)

    if not match:
        return False

    hour = int(match.group(1))
    minute = int(match.group(2))
    second = int(match.group(3) or 0)

    return 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59


def _parse_detail_entries(text):
    lines = [
        _clean(line)
        for line in str(text or "").splitlines()
        if _clean(line)
    ]
    times = []

    for line in lines:
        if _is_clock_time(line):
            times.append(line)

    start_time = times[0] if times else ""
    end_time = times[-1] if len(times) > 1 else ""

    detail_activity = ""
    activity_values = {
        "Work",
        "Left",
        "Absent",
        "Didn't come",
        "Didn’t come",
        "Did not come",
    }

    for line in lines:
        if line in activity_values:
            detail_activity = line
            break

    return start_time, end_time, " | ".join(lines), detail_activity


def _parse_detail_entry_rows(detail):
    entries = detail.get("entries", []) if isinstance(detail, dict) else []
    times = []
    activities = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        time_value = _clean(entry.get("time"))

        if _is_clock_time(time_value):
            times.append(time_value)

        activity = _clean(entry.get("activity"))

        if activity:
            activities.append(activity)

    start_time = times[0] if times else ""
    end_time = times[-1] if len(times) > 1 else ""
    detail_activity = activities[-1] if activities else ""
    detail_raw = _clean(detail.get("raw")) if isinstance(detail, dict) else ""

    return start_time, end_time, detail_raw, detail_activity


def _parse_grid_time_cells(cells):
    times = []

    for value in cells or []:
        text = _clean(value)
        if _is_clock_time(text):
            times.append(text)

    start_time = times[0] if times else ""
    end_time = times[1] if len(times) > 1 else ""

    return start_time, end_time


def _looks_not_worked(value):
    text = _clean(value).lower()
    return (
        not text
        or ("didn" in text and "come" in text)
        or text in {"did not come", "empty"}
    )


def _courier_name_from_grid_text(value):
    parsed = split_courier_text(value)
    return _clean(parsed.get("courier_name")) or _clean(value)


def _main_grid_rows():
    script = r"""
const rows = [];
const grids = [...document.querySelectorAll('.v-grid')];
const grid = grids[0] || document;
const rowEls = [...grid.querySelectorAll('tr')].filter(row => row.querySelectorAll('td.v-grid-cell').length >= 4);
const statusValues = new Set(['Work', 'Left', 'Absent', "Didn't come", 'Did not come']);
const allVisibleCells = [...grid.querySelectorAll('td.v-grid-cell')]
  .map(cell => {
    const rect = cell.getBoundingClientRect();
    return {
      rect,
      text: (cell.innerText || cell.textContent || '').trim(),
      center: rect.top + rect.height / 2,
    };
  })
  .filter(item => item.rect.width > 0 && item.rect.height > 0);

for (const row of rowEls) {
  const rowRect = row.getBoundingClientRect();
  const cells = [...row.querySelectorAll('td.v-grid-cell')].map(cell => (cell.innerText || cell.textContent || '').trim());
  if (!cells[0]) {
    continue;
  }

  const rowCenter = rowRect.top + rowRect.height / 2;
  const rowTexts = allVisibleCells
    .filter(item => Math.abs(item.center - rowCenter) <= Math.max(4, rowRect.height * 0.45))
    .sort((a, b) => a.rect.left - b.rect.left)
    .map(item => item.text)
    .filter(Boolean);
  const activity = rowTexts.find(text => statusValues.has(text)) || cells[3] || cells[2] || '';

  rows.push({
    name: cells[0],
    shift: cells[1] || '',
    activity,
    cells: rowTexts.length ? rowTexts : cells,
  });
}
return rows;
"""
    return _driver().execute_script(script) or []


def _scroll_main_grid_to_top():
    script = r"""
const grids = [...document.querySelectorAll('.v-grid')];
const grid = grids[0];
if (!grid) {
  return false;
}

const candidates = [grid, ...grid.querySelectorAll('*')];
let parent = grid.parentElement;
while (parent) {
  candidates.push(parent);
  parent = parent.parentElement;
}

const scrollable = candidates
  .filter(el => el.scrollHeight > el.clientHeight + 20)
  .sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight))[0];

if (!scrollable) {
  return false;
}

scrollable.scrollTop = 0;
return true;
"""
    return bool(_driver().execute_script(script))


def _scroll_main_grid_down():
    script = r"""
const grids = [...document.querySelectorAll('.v-grid')];
const grid = grids[0];
if (!grid) {
  return {moved: false, top: 0, maxTop: 0};
}

const candidates = [grid, ...grid.querySelectorAll('*')];
let parent = grid.parentElement;
while (parent) {
  candidates.push(parent);
  parent = parent.parentElement;
}

const scrollable = candidates
  .filter(el => el.scrollHeight > el.clientHeight + 20)
  .sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight))[0];

if (!scrollable) {
  window.scrollBy(0, Math.floor(window.innerHeight * 0.8));
  return {moved: false, top: window.scrollY || 0, maxTop: 0};
}

const before = scrollable.scrollTop;
const step = Math.max(120, Math.floor(scrollable.clientHeight * 0.75));
scrollable.scrollTop = Math.min(scrollable.scrollTop + step, scrollable.scrollHeight);
const after = scrollable.scrollTop;
return {
  moved: after > before,
  top: after,
  maxTop: Math.max(0, scrollable.scrollHeight - scrollable.clientHeight)
};
"""
    return _driver().execute_script(script) or {"moved": False}


def _click_main_row_by_name(name):
    script = r"""
const wanted = arguments[0];
const grids = [...document.querySelectorAll('.v-grid')];
const grid = grids[0] || document;
const rowEls = [...grid.querySelectorAll('tr')].filter(row => row.querySelectorAll('td.v-grid-cell').length >= 4);

for (const row of rowEls) {
  const firstCell = row.querySelector('td.v-grid-cell');
  const text = (firstCell && (firstCell.innerText || firstCell.textContent || '').trim()) || '';
  if (text === wanted) {
    firstCell.click();
    return true;
  }
}
return false;
"""
    return bool(_driver().execute_script(script, name))


def _install_vaadin_response_capture():
    script = r"""
window.__giritonAttendanceResponses = window.__giritonAttendanceResponses || [];

function patchResponses(root) {
  const nodes = [root, ...root.querySelectorAll('*')];

  for (const node of nodes) {
    if (!node || node.__giritonAttendancePatched || typeof node.setResponse !== 'function') {
      continue;
    }

    const original = node.setResponse;
    node.setResponse = function(response) {
      try {
        window.__giritonAttendanceResponses.push(response);
      } catch (error) {
      }
      return original.apply(this, arguments);
    };
    node.__giritonAttendancePatched = true;
  }
}

patchResponses(document);

if (!window.__giritonAttendancePatchInterval) {
  window.__giritonAttendancePatchInterval = window.setInterval(() => patchResponses(document), 500);
}

return true;
"""
    return bool(_driver().execute_script(script))


def install_vaadin_response_capture():
    return _install_vaadin_response_capture()


def _captured_vaadin_responses():
    script = r"""
const responses = window.__giritonAttendanceResponses || [];
window.__giritonAttendanceResponses = [];
return responses;
"""
    return _driver().execute_script(script) or []


def _merge_uidl_rows(rows, uidl_rows, work_date):
    by_key = {
        (_clean(row[0]), _clean(row[1])): row
        for row in rows
        if isinstance(row, list) and len(row) >= 2
    }

    for uidl_row in uidl_rows or []:
        if _clean(uidl_row.get("work_date")) != _clean(work_date):
            continue

        name = _clean(uidl_row.get("courier_name"))
        if not name:
            continue

        key = (_clean(work_date), name)
        raw_details = _clean(uidl_row.get("raw_details"))
        activity = _clean(uidl_row.get("activity_status"))
        start_time = _clean(uidl_row.get("checkin_start"))
        end_time = _clean(uidl_row.get("checkin_end"))
        shift_text = _clean(uidl_row.get("shift_text"))

        if key not in by_key:
            row = [
                work_date,
                name,
                shift_text,
                activity,
                start_time,
                end_time,
                raw_details,
            ]
            rows.append(row)
            by_key[key] = row
            continue

        row = by_key[key]
        if shift_text and (not _clean(row[2]) or _clean(row[2]).upper() == "EMPTY"):
            row[2] = shift_text
        if activity and (_looks_not_worked(row[3]) or activity != _clean(row[3])):
            row[3] = activity
        if start_time:
            row[4] = start_time
        if end_time:
            row[5] = end_time
        if raw_details:
            row[6] = raw_details

    return rows


def _uidl_attendance_rows_from_captured(work_date):
    uidl_rows = []
    for response in _captured_vaadin_responses():
        uidl_rows.extend(
            parse_attendance_uidl_rows(
                response,
                default_work_date=work_date,
            )
        )

    by_key = {}
    for row in uidl_rows:
        name = _clean(row.get("courier_name")) if isinstance(row, dict) else ""
        row_date = _clean(row.get("work_date")) if isinstance(row, dict) else ""
        if row_date != _clean(work_date) or not name:
            continue
        by_key[(row_date, name)] = row

    return list(by_key.values())


def scrape_attendance_rows_fast(work_date, wait_seconds=2.0):
    _install_vaadin_response_capture()
    time.sleep(float(wait_seconds or 0))
    return _uidl_attendance_rows_from_captured(work_date)


def _detail_entries_for_name(name):
    script = r"""
const wanted = arguments[0] || '';
const original = arguments[1] || '';
const activities = new Set(['Work', 'Left', 'Absent', "Didn't come", 'Did not come']);

function clean(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function isVisible(el) {
  if (!el) {
    return false;
  }

  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function isClockTime(value) {
  const match = clean(value).match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);

  if (!match) {
    return false;
  }

  const hour = Number(match[1]);
  const minute = Number(match[2]);
  const second = Number(match[3] || 0);
  return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59 && second >= 0 && second <= 59;
}

function slotText(slot) {
  if (!slot) {
    return '';
  }

  try {
    const assigned = typeof slot.assignedElements === 'function'
      ? slot.assignedElements({flatten: true})
      : [];

    const assignedText = assigned
      .map(el => el.innerText || el.textContent || '')
      .join('\n')
      .trim();

    if (assignedText) {
      return assignedText;
    }
  } catch (error) {
  }

  return slot.innerText || slot.textContent || '';
}

function addEntriesFromText(text, source, out) {
  const lines = String(text || '')
    .split(/\r?\n/)
    .map(clean)
    .filter(Boolean);

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];

    if (!activities.has(line)) {
      continue;
    }

    for (const nextLine of lines.slice(index + 1, index + 8)) {
      if (isClockTime(nextLine)) {
        out.push({
          activity: line,
          time: clean(nextLine),
          source,
        });
        break;
      }
    }
  }
}

function addEntriesFromRows(root, source, out) {
  const rows = [
    ...root.querySelectorAll('tr'),
    ...root.querySelectorAll('.v-grid-row, [role="row"]'),
  ];

  for (const row of rows) {
    const cells = [...row.querySelectorAll('td, th, .v-grid-cell, [role="cell"], [role="gridcell"]')]
      .map(cell => clean(cell.innerText || cell.textContent || ''))
      .filter(Boolean);

    const activity = cells.find(cell => activities.has(cell));
    const time = cells.find(cell => isClockTime(cell));

    if (activity && time) {
      out.push({
        activity,
        time,
        source,
      });
    }
  }
}

function addCurrentDetailEntries(out, rawParts) {
  const roots = [...document.querySelectorAll('body *')]
    .filter(isVisible)
    .map(el => {
      const text = el.innerText || el.textContent || '';
      return {
        el,
        text,
        cleanText: clean(text),
        length: text.length,
      };
    })
    .filter(item => {
      const text = item.cleanText;
      return text.includes('Activity')
        && text.includes('Time')
        && text.includes('Details')
        && item.length < 6000;
    })
    .sort((a, b) => a.length - b.length);

  for (const item of roots) {
    const before = out.length;
    addEntriesFromRows(item.el, 'current-detail-rows', out);
    addEntriesFromText(item.text, 'current-detail-text', out);

    if (out.length > before) {
      rawParts.push(item.text);
      return true;
    }
  }

  return false;
}

function findNameNodes() {
  const visibleNodes = [...document.querySelectorAll('body *')]
    .filter(isVisible)
    .sort((a, b) => clean(a.innerText || a.textContent || '').length - clean(b.innerText || b.textContent || '').length);
  const wantedNodes = visibleNodes.filter(el => {
    const text = clean(el.innerText || el.textContent || '');
    return text === wanted || (wanted && text.includes(wanted));
  });

  if (wantedNodes.length) {
    return wantedNodes;
  }

  return visibleNodes.filter(el => {
    const text = clean(el.innerText || el.textContent || '');
    return text === original || (original && text.includes(original));
  });
}

const entries = [];
const rawParts = [];
const roots = [];

const usedCurrentDetail = addCurrentDetailEntries(entries, rawParts);

if (!usedCurrentDetail) {
for (const node of findNameNodes()) {
  let divAncestor = node;
  let divHops = 0;

  while (divAncestor && divHops < 2) {
    divAncestor = divAncestor.parentElement;

    if (divAncestor && String(divAncestor.tagName || '').toLowerCase() === 'div') {
      divHops += 1;
    }
  }

  if (divAncestor) {
    const slots = [...divAncestor.querySelectorAll('slot')];
    const secondSlotText = slotText(slots[1]);

    if (secondSlotText) {
      rawParts.push(secondSlotText);
      addEntriesFromText(secondSlotText, 'second-slot', entries);
    }
  }

  let parent = node;

  for (let index = 0; index < 8 && parent; index += 1) {
    const text = parent.innerText || parent.textContent || '';

    if (text.includes('Entries') && text.includes('Activity') && text.includes('Time')) {
      roots.push(parent);
    }

    parent = parent.parentElement;
  }
}
}

for (const root of roots) {
  const text = root.innerText || root.textContent || '';
  rawParts.push(text);
  addEntriesFromRows(root, 'rows', entries);
  addEntriesFromText(text, 'text', entries);

  if (entries.length) {
    break;
  }
}

const seen = new Set();
const uniqueEntries = [];

for (const entry of entries) {
  const key = `${entry.activity}|${entry.time}`;

  if (!seen.has(key)) {
    seen.add(key);
    uniqueEntries.push(entry);
  }
}

return {
  wanted,
  original,
  entries: uniqueEntries,
  raw: rawParts.join('\n---\n'),
};
"""
    return _driver().execute_script(
        script,
        _reverse_name(name),
        _clean(name),
    ) or {}


def _detail_text(name=""):
    script = r"""
const wanted = arguments[0] || '';
const timePattern = /(^|\s)\d{1,2}:\d{2}(:\d{2})?(\s|$)/;
const candidates = [...document.querySelectorAll('body *')]
  .filter(el => {
    const text = (el.innerText || '').trim();
    const rect = el.getBoundingClientRect();
    return rect.width > 0
      && rect.height > 0
      && text.includes('Entries')
      && text.includes('Activity')
      && text.includes('Time');
  })
  .map(el => {
    const text = el.innerText || '';
    return {
      text,
      hasTime: timePattern.test(text),
      hasName: wanted ? text.includes(wanted) : false,
      length: text.length,
    };
  })
  .sort((a, b) => {
    if (a.hasTime !== b.hasTime) {
      return a.hasTime ? -1 : 1;
    }

    if (a.hasName !== b.hasName) {
      return a.hasName ? -1 : 1;
    }

    return a.length - b.length;
  });

if (candidates.length) {
  return candidates[0].text || '';
}

const grids = [...document.querySelectorAll('.v-grid')];
if (grids.length > 1) {
  return grids.slice(1).map(g => g.innerText || '').join('\n');
}
return '';
"""
    return _driver().execute_script(script, name) or ""


def scrape_attendance_rows(work_date):
    rows = []
    seen = set()
    stable_pages = 0

    _install_vaadin_response_capture()
    _scroll_main_grid_to_top()
    time.sleep(1.0)

    for _ in range(80):
        before_count = len(seen)

        for base_row in _main_grid_rows():
            display_name = _clean(base_row.get("name"))
            name = _courier_name_from_grid_text(display_name)
            if not display_name or display_name in seen:
                continue

            seen.add(display_name)
            shift = _clean(base_row.get("shift"))
            activity = _clean(base_row.get("activity"))
            original_activity = activity

            if not shift or shift.upper() == "EMPTY":
                continue

            if _click_main_row_by_name(display_name):
                time.sleep(0.8)

            detail = _detail_text(display_name)
            start_time, end_time, detail_raw, detail_activity = _parse_detail_entries(
                detail
            )

            if (start_time or end_time) and (
                not activity or activity in {"Didn't come", "Didn’t come", "Did not come"}
            ):
                activity = detail_activity or "Work"

            if (start_time or end_time) and _looks_not_worked(activity):
                activity = detail_activity or ("Left" if end_time else "Work")

            name_detail = _detail_entries_for_name(display_name)
            (
                name_start_time,
                name_end_time,
                name_detail_raw,
                name_detail_activity,
            ) = _parse_detail_entry_rows(name_detail)

            detail_is_too_broad = (
                name_detail_raw.count("Just in Time Kft") > 1
                or name_detail_raw.startswith("Shift Project Activity")
            )

            if (name_start_time or name_end_time) and not detail_is_too_broad:
                start_time = name_start_time
                end_time = name_end_time
                detail_raw = name_detail_raw
                detail_activity = name_detail_activity

                if _looks_not_worked(activity):
                    activity = detail_activity or ("Left" if end_time else "Work")
            else:
                start_time = ""
                end_time = ""
                detail_raw = "" if detail_is_too_broad else name_detail_raw
                activity = original_activity

            rows.append([
                work_date,
                name,
                shift,
                activity,
                start_time,
                end_time,
                detail_raw,
            ])

        scroll_state = _scroll_main_grid_down()
        time.sleep(0.6)

        if len(seen) == before_count:
            stable_pages += 1
        else:
            stable_pages = 0

        if (
            not scroll_state.get("moved")
            or scroll_state.get("top", 0) >= scroll_state.get("maxTop", 0) - 3
        ) and stable_pages >= 2:
            break

    uidl_rows = []
    for response in _captured_vaadin_responses():
        uidl_rows.extend(
            parse_attendance_uidl_rows(
                response,
                default_work_date=work_date,
            )
        )

    if uidl_rows:
        rows = _merge_uidl_rows(
            rows,
            uidl_rows,
            work_date,
        )

    return rows
