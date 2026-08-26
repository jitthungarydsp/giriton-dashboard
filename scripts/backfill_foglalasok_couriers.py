import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.foglalasok_db import backfill_booking_couriers_from_master


def main():
    result = backfill_booking_couriers_from_master()
    print(
        "FOGLALASOK_COURIER_BACKFILL "
        f"checked={result.get('checked', 0)} "
        f"updated={result.get('updated', 0)}"
    )


if __name__ == "__main__":
    main()
