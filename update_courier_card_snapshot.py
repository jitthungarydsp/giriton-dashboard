import argparse

from resources.courier_card_snapshot import safe_write_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--month",
        default=None,
        help="Honap EEEE-HH formaban, peldaul 2026-06. Uresen az aktualis honap.",
    )
    args = parser.parse_args()

    result = safe_write_snapshot(
        month_text=args.month,
        preserve_existing=True,
    )
    print(result)


if __name__ == "__main__":
    main()
