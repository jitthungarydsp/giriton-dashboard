import argparse
import sys
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from resources.supabase_raw import get_supabase_config, raise_for_supabase_error


TABLES = [
    "ops_attendance_muszakpro_comparison",
    "raw_fetch_attendance_shifts",
]


def headers():
    _supabase_url, service_role_key = get_supabase_config()

    if not service_role_key:
        raise RuntimeError(
            "Hianyzik a SUPABASE_SERVICE_ROLE_KEY beallitas."
        )

    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }


def get_url():
    supabase_url, _service_role_key = get_supabase_config()

    if not supabase_url:
        raise RuntimeError(
            "Hianyzik a SUPABASE_URL beallitas."
        )

    return supabase_url


def select_collections(work_date):
    supabase_url = get_url()
    endpoint = (
        f"{supabase_url}/rest/v1/ops_attendance_muszakpro_comparison"
        "?select=collection_id,collected_at"
        f"&work_date=eq.{work_date}"
        "&order=collected_at.desc"
    )
    response = requests.get(
        endpoint,
        headers=headers(),
        timeout=60,
    )
    raise_for_supabase_error(response)
    seen = {}

    for row in response.json():
        collection_id = row.get("collection_id")

        if collection_id and collection_id not in seen:
            seen[collection_id] = row.get("collected_at")

    return [
        {
            "collection_id": collection_id,
            "collected_at": collected_at,
        }
        for collection_id, collected_at in seen.items()
    ]


def delete_collection(table_name, collection_id):
    supabase_url = get_url()
    endpoint = (
        f"{supabase_url}/rest/v1/{table_name}"
        f"?collection_id=eq.{collection_id}"
    )
    response = requests.delete(
        endpoint,
        headers={
            **headers(),
            "Prefer": "return=minimal",
        },
        timeout=60,
    )
    raise_for_supabase_error(response)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Regi attendance vs MuszakPro collectionok takaritasa."
    )
    parser.add_argument(
        "--work-date",
        required=True,
        help="Takaritando nap YYYY-MM-DD formatumban.",
    )
    parser.add_argument(
        "--keep-latest",
        type=int,
        default=1,
        help="Hany legfrissebb collection maradjon meg.",
    )
    parser.add_argument(
        "--collection-id",
        action="append",
        default=[],
        help="Konkret collection_id torlese. Tobbszor is megadhato.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Tenyleges torles. Enelkul csak kiirja, mit torolne.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    collections = select_collections(
        args.work_date
    )
    explicit_ids = set(args.collection_id or [])

    if explicit_ids:
        delete_ids = [
            collection["collection_id"]
            for collection in collections
            if collection["collection_id"] in explicit_ids
        ]
    else:
        keep_latest = max(args.keep_latest, 0)
        delete_ids = [
            collection["collection_id"]
            for collection in collections[keep_latest:]
        ]

    print(
        f"WORK_DATE={args.work_date}"
    )
    print(
        f"COLLECTIONS={len(collections)}"
    )

    for index, collection in enumerate(collections, start=1):
        marker = "DELETE" if collection["collection_id"] in delete_ids else "KEEP"
        print(
            f"{marker} #{index} {collection['collection_id']} {collection.get('collected_at')}"
        )

    if not delete_ids:
        print("Nincs torlendo collection.")
        return

    if not args.apply:
        print("DRY RUN, torles nem tortent. Eleshez add meg: --apply")
        return

    for collection_id in delete_ids:
        for table_name in TABLES:
            delete_collection(
                table_name,
                collection_id,
            )
        print(
            f"TOROLVE {collection_id}"
        )


if __name__ == "__main__":
    main()
