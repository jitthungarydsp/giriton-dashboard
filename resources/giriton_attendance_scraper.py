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

    return start_time, end_time, " | ".join(lines)


def _main_grid_rows():
    script = r"""
const rows = [];
const grids = [...document.querySelectorAll('.v-grid')];
const grid = grids[0] || document;
const rowEls = [...grid.querySelectorAll('tr')].filter(row => row.querySelectorAll('td.v-grid-cell').length >= 4);

for (const row of rowEls) {
  const cells = [...row.querySelectorAll('td.v-grid-cell')].map(cell => (cell.innerText || cell.textContent || '').trim());
  if (!cells[0]) {
    continue;
  }
  rows.push({
    name: cells[0],
    shift: cells[1] || '',
    activity: cells[3] || cells[2] || '',
  });
}
return rows;
"""
    return _driver().execute_script(script) or []


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


def _detail_text():
    script = r"""
const grids = [...document.querySelectorAll('.v-grid')];
const main = grids[0];
const candidates = [...document.querySelectorAll('body *')]
  .filter(el => {
    const text = (el.innerText || '').trim();
    return text.includes('Entries') && text.includes('Activity') && text.includes('Time');
  })
  .sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);

if (candidates.length) {
  return candidates[0].innerText || '';
}

if (grids.length > 1) {
  return grids.slice(1).map(g => g.innerText || '').join('\n');
}
return '';
"""
    return _driver().execute_script(script) or ""


def scrape_attendance_rows(work_date):
    rows = []
    seen = set()

    for base_row in _main_grid_rows():
        name = _clean(base_row.get("name"))
        if not name or name in seen:
            continue

        seen.add(name)
        shift = _clean(base_row.get("shift"))
        activity = _clean(base_row.get("activity"))

        if _click_main_row_by_name(name):
            time.sleep(0.4)

        detail = _detail_text()
        start_time, end_time, detail_raw = _parse_detail_entries(detail)

        rows.append([
            work_date,
            name,
            shift,
            activity,
            start_time,
            end_time,
            detail_raw,
        ])

    return rows
