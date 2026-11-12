"""Insurance end dates apply to both monthly insurance and reserve deductions."""
from datetime import date, datetime


def insurance_end_date(value):
    if value is None or str(value).strip() in {'', 'None', 'NaT', 'nan'}:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value).strip()[:10])


def insurance_cancelled_for_period(row, period_start):
    end = insurance_end_date((row or {}).get('insurance_end_date'))
    period = insurance_end_date(period_start) or date.today().replace(day=1)
    # The end date is inclusive. Monthly fees stop in the following month.
    return end is not None and period.replace(day=1) > end


def insurance_active_for_period(row, period_start, active=None):
    if active is None:
        active = str((row or {}).get('insurance_active')).strip().casefold() in {'true', 't', '1', 'yes', 'igen'}
    return bool(active) and not insurance_cancelled_for_period(row, period_start)
