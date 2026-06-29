import os

from resources.shift_reconciliation_sheet import rebuild_shift_reconciliation


if __name__ == "__main__":
    start_date = os.getenv("GIRITION_START_DATE") or None
    days = int(os.getenv("GIRITION_DAYS", "10"))
    records = rebuild_shift_reconciliation(
        start_date=start_date,
        days=days,
    )
    print(f"SHIFT_RECONCILIATION_ROWS={len(records)}")
