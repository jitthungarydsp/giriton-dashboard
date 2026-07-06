import re
import time

from robot.libraries.BuiltIn import BuiltIn


def _selenium():
    return BuiltIn().get_library_instance("SeleniumLibrary")


def _driver():
    return _selenium().driver


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_detail_entries(text):
    lines = [
        _clean(line)
        for line in str(text or "").splitlines()
        if _clean(line)
    ]
    times = []

    for line in lines:
        if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", line):
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


def _parse_grid_time_cells(cells):
    times = []

    for value in cells or []:
        text = _clean(value)
        if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", text):
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


def _main_grid_rows():
    script = r"""
const rows = [];
const grids = [...document.querySelectorAll('.v-grid')];
const grid = grids[0] || document;
const rowEls = [...grid.querySelectorAll('tr')].filter(row => row.querySelectorAll('td.v-grid-cell').length >= 4);
const statusValues = new Set(['Work', 'Left', 'Absent', "Didn't come", 'Did not come']);
const allVisibleCells = [...document.querySelectorAll('td.v-grid-cell')]
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

    _scroll_main_grid_to_top()
    time.sleep(1.0)

    for _ in range(80):
        before_count = len(seen)

        for base_row in _main_grid_rows():
            name = _clean(base_row.get("name"))
            if not name or name in seen:
                continue

            seen.add(name)
            shift = _clean(base_row.get("shift"))
            activity = _clean(base_row.get("activity"))

            if _click_main_row_by_name(name):
                time.sleep(0.8)

            detail = _detail_text(name)
            start_time, end_time, detail_raw, detail_activity = _parse_detail_entries(
                detail
            )

            if not start_time and not end_time:
                start_time, end_time = _parse_grid_time_cells(
                    base_row.get("cells", [])
                )

            if (start_time or end_time) and (
                not activity or activity in {"Didn't come", "Didn’t come", "Did not come"}
            ):
                activity = detail_activity or "Work"

            if (start_time or end_time) and _looks_not_worked(activity):
                activity = detail_activity or ("Left" if end_time else "Work")

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

    return rows
