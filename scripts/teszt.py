import argparse
import json
import os
import subprocess
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests
def import_target_reserve_from_sheet():
    balances = read_target_reserve_balances()

    rows = []

    for courier_id, opening_balance in balances.items():
        rows.append({
            "courier_id": int(courier_id),
            "opening_balance_huf": int(opening_balance),
            "current_balance_huf": int(opening_balance),
            "insurance_active": True,
        })

    config = get_supabase_config()

    response = requests.post(
        f"{config['url']}/rest/v1/courier_target_reserve",
        headers={
            "apikey": config["key"],
            "Authorization": f"Bearer {config['key']}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        params={
            "on_conflict": "courier_id",
        },
        json=rows,
        timeout=60,
    )

    raise_for_supabase_error(response)