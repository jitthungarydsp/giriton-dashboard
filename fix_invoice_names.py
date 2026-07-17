from pathlib import Path

page_path = Path("page/invoice_summary.py")
resource_path = Path("resources/invoice_summary.py")

if not page_path.exists():
    raise SystemExit("Nem található: page/invoice_summary.py")

if not resource_path.exists():
    raise SystemExit("Nem található: resources/invoice_summary.py")


def replace_once(text, old, new, label):
    if old not in text:
        raise RuntimeError(f"Nem található a cserélendő rész: {label}")

    return text.replace(old, new, 1)


# -------------------------------------------------------------------
# page/invoice_summary.py
# -------------------------------------------------------------------

page = page_path.read_text(encoding="utf-8")

old_imports = '''from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
'''

new_imports = '''from datetime import date
from io import BytesIO
from pathlib import Path
import re
import unicodedata

import pandas as pd
'''

if "import unicodedata" not in page:
    page = replace_once(
        page,
        old_imports,
        new_imports,
        "re és unicodedata import",
    )


old_normalize = '''def normalize_name(value):
    return " ".join(str(value or "").strip().casefold().split())
'''

alternative_old_normalize = '''def normalize_name(value):
    return normalize_person_key(value)
'''

new_normalize = '''def normalize_person_key(value):
    """
    Futárnév-egyeztető kulcs.

    Például:
    - Papp Nikolett
    - Papp 7486 Nikolett

    ugyanahhoz a futárhoz fog tartozni.
    """
    text = unicodedata.normalize(
        "NFKD",
        str(value or "").strip().casefold(),
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    tokens = re.findall(r"[a-z0-9]+", text)

    # A névben szereplő Courier ID figyelmen kívül hagyása.
    tokens = [
        token
        for token in tokens
        if not (
            token.isdigit()
            and 3 <= len(token) <= 6
        )
    ]

    return " ".join(sorted(tokens))


def normalize_name(value):
    return normalize_person_key(value)
'''

if "def normalize_person_key(value):" not in page:
    if old_normalize in page:
        page = replace_once(
            page,
            old_normalize,
            new_normalize,
            "normalize_name",
        )
    elif alternative_old_normalize in page:
        page = replace_once(
            page,
            alternative_old_normalize,
            new_normalize,
            "normalize_name már részben módosítva",
        )
    else:
        raise RuntimeError(
            "Nem található a normalize_name függvény."
        )


old_filter = '''def filter_by_driver(df, selected_driver):
    if df.empty or selected_driver == "Mind":
        return df

    return df[
        df["driver_name"].astype(str) == selected_driver
    ].copy()
'''

new_filter = '''def filter_by_driver(df, selected_driver):
    if (
        df is None
        or df.empty
        or selected_driver == "Mind"
    ):
        return df

    if "driver_name" not in df.columns:
        return df.iloc[0:0].copy()

    selected_key = normalize_person_key(selected_driver)

    return df[
        df["driver_name"]
        .astype(str)
        .map(normalize_person_key)
        == selected_key
    ].copy()
'''

if old_filter in page:
    page = replace_once(
        page,
        old_filter,
        new_filter,
        "filter_by_driver",
    )


old_data = '''    final_df = data["final"]
    summary_df = data["summary"]
    bonus_df = data["bonus"]
    penalty_df = data["penalties"]
    manual_df = data["manual"]
    day_rates_df = data.get("day_rates", pd.DataFrame())
    raw_route_df = data.get("routes", pd.DataFrame())
'''

new_data = '''    final_df = data.get("final", pd.DataFrame())
    summary_df = data.get("summary", pd.DataFrame())
    bonus_df = data.get("bonus", pd.DataFrame())
    penalty_df = data.get("penalties", pd.DataFrame())
    manual_df = data.get("manual", pd.DataFrame())
    atm_balance_df = data.get("atm_balance", pd.DataFrame())
    customer_rating_df = data.get(
        "customer_rating",
        pd.DataFrame(),
    )
    monthly_adjustment_df = data.get(
        "monthly_adjustments",
        pd.DataFrame(),
    )
    day_rates_df = data.get("day_rates", pd.DataFrame())
    raw_route_df = data.get("routes", pd.DataFrame())
'''

if old_data in page:
    page = replace_once(
        page,
        old_data,
        new_data,
        "külső elszámolási források betöltése",
    )


old_driver_section = '''    all_filtered_final_df = final_df.copy()

    drivers = sorted(
        value
        for value in all_filtered_final_df.get(
            "driver_name",
            pd.Series(dtype=str),
        ).dropna().astype(str).unique()
        if value.strip()
    )

    render_invoice_delivery_status(
        drivers,
        start_date,
    )

    selected_driver = col4.selectbox(
        "Futar",
        ["Mind"] + drivers,
        key="invoice_driver_filter",
    )
    final_df = filter_by_driver(
        final_df,
        selected_driver,
    )
'''

new_driver_section = '''    all_filtered_final_df = final_df.copy()

    driver_names_by_key = {}


    def add_driver_names(frame):
        if (
            frame is None
            or frame.empty
            or "driver_name" not in frame.columns
        ):
            return

        for value in (
            frame["driver_name"]
            .dropna()
            .astype(str)
        ):
            name = value.strip()

            if not name:
                continue

            key = normalize_person_key(name)

            if not key:
                continue

            current_name = driver_names_by_key.get(key)

            # A Courier ID-t is tartalmazó, teljesebb nevet mutatjuk.
            if (
                not current_name
                or len(name) > len(current_name)
            ):
                driver_names_by_key[key] = name


    add_driver_names(all_filtered_final_df)
    add_driver_names(bonus_df)
    add_driver_names(penalty_df)
    add_driver_names(manual_df)
    add_driver_names(atm_balance_df)
    add_driver_names(customer_rating_df)
    add_driver_names(monthly_adjustment_df)

    drivers = sorted(
        driver_names_by_key.values(),
        key=normalize_person_key,
    )

    render_invoice_delivery_status(
        drivers,
        start_date,
    )

    selected_driver = col4.selectbox(
        "Futar",
        ["Mind"] + drivers,
        key="invoice_driver_filter",
    )

    final_df = filter_by_driver(
        final_df,
        selected_driver,
    )
    bonus_df = filter_by_driver(
        bonus_df,
        selected_driver,
    )
    penalty_df = filter_by_driver(
        penalty_df,
        selected_driver,
    )
    manual_df = filter_by_driver(
        manual_df,
        selected_driver,
    )
    atm_balance_df = filter_by_driver(
        atm_balance_df,
        selected_driver,
    )
    customer_rating_df = filter_by_driver(
        customer_rating_df,
        selected_driver,
    )
    monthly_adjustment_df = filter_by_driver(
        monthly_adjustment_df,
        selected_driver,
    )
'''

if old_driver_section not in page:
    raise RuntimeError(
        "Nem található a régi futárlista és szűrés blokk."
    )

page = replace_once(
    page,
    old_driver_section,
    new_driver_section,
    "teljes futárlista",
)


old_summary_call = '''    driver_summary = build_driver_invoice_summary(
        final_df,
        bonus_df,
        penalty_df,
        manual_df,
        day_rates_df,
        raw_route_df,
        previous_routes_df=data.get("previous_routes", pd.DataFrame()),
        loyalty_profiles_df=data.get("loyalty_profiles", pd.DataFrame()),
        bookings_df=data.get("bookings", pd.DataFrame()),
        loyalty_acceptance_df=data.get("loyalty_acceptance", pd.DataFrame()),
        period_start=start_date,
    )
'''

new_summary_call = '''    driver_summary = build_driver_invoice_summary(
        final_df,
        bonus_df=bonus_df,
        penalty_df=penalty_df,
        manual_df=manual_df,
        day_rates_df=day_rates_df,
        raw_route_df=raw_route_df,
        previous_routes_df=data.get(
            "previous_routes",
            pd.DataFrame(),
        ),
        loyalty_profiles_df=data.get(
            "loyalty_profiles",
            pd.DataFrame(),
        ),
        bookings_df=data.get(
            "bookings",
            pd.DataFrame(),
        ),
        loyalty_acceptance_df=data.get(
            "loyalty_acceptance",
            pd.DataFrame(),
        ),
        atm_balance_df=atm_balance_df,
        customer_rating_df=customer_rating_df,
        monthly_adjustment_df=monthly_adjustment_df,
        period_start=start_date,
    )
'''

if old_summary_call in page:
    page = replace_once(
        page,
        old_summary_call,
        new_summary_call,
        "build_driver_invoice_summary hívás",
    )


old_bulk_filter = '''                    if "driver_name" in single_routes.columns:
                        single_routes = single_routes[
                            single_routes["driver_name"].astype(str) == bulk_driver_name
                        ].copy()
'''

new_bulk_filter = '''                    if "driver_name" in single_routes.columns:
                        bulk_driver_key = normalize_person_key(
                            bulk_driver_name
                        )
                        single_routes = single_routes[
                            single_routes["driver_name"]
                            .astype(str)
                            .map(normalize_person_key)
                            == bulk_driver_key
                        ].copy()
'''

if old_bulk_filter in page:
    page = replace_once(
        page,
        old_bulk_filter,
        new_bulk_filter,
        "tömeges feltöltés névszűrése",
    )


page_path.write_text(page, encoding="utf-8")


# -------------------------------------------------------------------
# resources/invoice_summary.py
# -------------------------------------------------------------------

resource = resource_path.read_text(encoding="utf-8")

old_resource_normalizer = '''def normalize_person_key(value):
    text = unicodedata.normalize("NFKD", normalize_text(value).casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    tokens = re.findall(r"[a-z0-9]+", text)
    return " ".join(sorted(tokens))
'''

new_resource_normalizer = '''def normalize_person_key(value):
    text = unicodedata.normalize(
        "NFKD",
        normalize_text(value).casefold(),
    )

    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )

    tokens = re.findall(r"[a-z0-9]+", text)

    # A futár nevébe írt Courier ID ne akadályozza a párosítást.
    tokens = [
        token
        for token in tokens
        if not (
            token.isdigit()
            and 3 <= len(token) <= 6
        )
    ]

    return " ".join(sorted(tokens))
'''

if old_resource_normalizer not in resource:
    raise RuntimeError(
        "Nem található a resources normalize_person_key függvénye."
    )

resource = replace_once(
    resource,
    old_resource_normalizer,
    new_resource_normalizer,
    "resources névnormalizálás",
)

resource_path.write_text(resource, encoding="utf-8")

print()
print("A javítás sikeresen elkészült.")
print("Módosítva:")
print("  - page/invoice_summary.py")
print("  - resources/invoice_summary.py")
