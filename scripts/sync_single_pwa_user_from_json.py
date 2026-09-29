from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from resources.pwa_users_db import sync_single_pwa_user_from_json_users


USERS_FILE = PROJECT_ROOT / "data" / "users.json"


def load_json_users() -> list[dict[str, Any]]:
    with USERS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file).get("users", [])


def sync_user(courier_id: str) -> dict[str, Any]:
    return sync_single_pwa_user_from_json_users(load_json_users(), courier_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Egy PWA user átemelése users.json-ból pwa_users DB-be.")
    parser.add_argument("--courier-id", required=True)
    args = parser.parse_args()

    row = sync_user(args.courier_id)
    print("OK: PWA user DB-be szinkronizálva.")
    print(f"courier_id={row.get('courier_id')}")
    print(f"username={row.get('username')}")
    print(f"active={row.get('active')}")


if __name__ == "__main__":
    main()
