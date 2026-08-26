import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.foglalasok_db import export_courier_master_to_id_sheet


def main():
    result = export_courier_master_to_id_sheet()
    print(
        "COURIER_MASTER_ID_SHEET_EXPORT "
        f"sheet={result.get('sheet')} "
        f"rows={result.get('rows', 0)}"
    )


if __name__ == "__main__":
    main()
