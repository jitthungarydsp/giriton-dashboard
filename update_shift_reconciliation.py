from resources.shift_reconciliation_sheet import rebuild_shift_reconciliation


if __name__ == "__main__":
    records = rebuild_shift_reconciliation(days=10)
    print(f"SHIFT_RECONCILIATION_ROWS={len(records)}")
