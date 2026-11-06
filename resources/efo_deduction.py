"""Daily EFO deductions. No database writes or changes to manual entries."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class EfoCalculationError(ValueError):
    pass


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        raise EfoCalculationError(f"EFO: nem értelmezhető munkanap/dátum: {value!r}") from None


def calculate_efo_adjustments(courier_id, worked_dates, assignments, period_start, period_end,
                              manual_adjustments=()):
    """One charge per distinct worked date, only within an active assignment.

    Ambiguous rules and existing manual EFO deductions block recalculation;
    neither is silently added twice or replaced based on a guessed amount.
    """
    rules = []
    for item in assignments:
        if str(item.get("courier_id")) != str(courier_id):
            continue
        if item.get("is_active") is False or item.get("deleted_at"):
            continue
        start = _date(item.get("valid_from"))
        end = _date(item["valid_to"]) if item.get("valid_to") else date.max
        if end < period_start or start > period_end:
            continue
        try:
            rate = Decimal(str(item.get("daily_deduction_huf")))
        except InvalidOperation:
            raise EfoCalculationError("EFO: hibás napi díj.") from None
        if not rate.is_finite() or rate < 0 or rate != rate.to_integral_value() or end < start:
            raise EfoCalculationError("EFO: hibás napi díj vagy érvényességi időszak.")
        rules.append((start, end, int(rate), str(item.get("id") or "")))
    if not rules:
        return []
    deductions = []
    for day in sorted({_date(value) for value in worked_dates}):
        if not period_start <= day <= period_end:
            continue
        matching = [rule for rule in rules if rule[0] <= day <= rule[1]]
        if len(matching) > 1:
            raise EfoCalculationError(f"EFO: átfedő bejelentési időszakok ({courier_id}, {day}).")
        if not matching or matching[0][2] == 0:
            continue
        _, _, rate, rule_id = matching[0]
        deductions.append({
            "id": f"efo:{courier_id}:{day}", "courier_id": str(courier_id),
            "adjustment_type": "correction_deduction", "amount_huf": rate,
            "effective_date": day.isoformat(), "valid_from": day.isoformat(),
            "valid_to": day.isoformat(), "created_by": "automatic_efo",
            "note": f"EFO napi levonás | {day} | 1 nap × {rate:,} Ft | Paraméter: {rule_id}".replace(",", " "),
        })
    if deductions:
        for item in manual_adjustments:
            if item.get("adjustment_type") not in {"malus", "correction_deduction", "manual_correction_deduction", "other_expense"}:
                continue
            if not float(item.get("amount_huf") or 0) or item.get("created_by") == "automatic_efo":
                continue
            if re.search(r"\befo\b|egyszerűsített foglalkoztat", str(item.get("note") or ""), re.I):
                raise EfoCalculationError(
                    f"EFO: {courier_id} futárnál kézi EFO-levonás is van ebben a hónapban "
                    f"(tétel: {item.get('id', '-')}). Ellenőrizd a kézi tételt; az automatikus "
                    "elszámolás a dupla levonás elkerüléséig nem menthető."
                )
    return deductions
