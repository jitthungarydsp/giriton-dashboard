"""Identify the workbook's separately supplied out-of-contract bonuses."""
import re
import unicodedata
import math

BONUS_LABEL = "Szerződésen kívüli bónusz"
BONUS_SOURCE = "Out_of_contract_Bonus Routes"


def is_out_of_contract_bonus_sheet(value: object) -> bool:
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', text) in {
        'outofcontractbonusroutes', 'outofcontractbonusroute', 'outofcontractbonus',
    }


def summary_out_of_contract_bonus(summary) -> float | None:
    """Return a known amount, preserving the difference between missing and zero."""
    value = summary.get('other_route_bonus_huf')
    if value is None or value == '':
        return None
    amount = float(value)
    if not math.isfinite(amount):
        raise ValueError('Érvénytelen szerződésen kívüli bónusz a havi elszámolásban.')
    return amount


def enrich_out_of_contract_bonus(row, summary) -> dict:
    """Hydrate even a cached/incomplete dashboard row before recalculation."""
    enriched = dict(row)
    amount = summary_out_of_contract_bonus(summary)
    if amount is not None:
        enriched[BONUS_LABEL] = amount
    return enriched


def validate_out_of_contract_snapshot_consistency(finance_rows, sources) -> None:
    """Never publish a bonus that disagrees with the supplied monthly source."""
    summary = next((s.get('payload') for s in sources or []
                    if s.get('source_key') == 'settlement_summary'), None)
    if not isinstance(summary, dict):
        return
    expected = summary_out_of_contract_bonus(summary)
    if expected is None:
        return
    items = [r for r in finance_rows if r.get('item_key') == 'address_bonus_kifli']
    actual = float(items[0]['amount_value']) if len(items) == 1 else float('nan')
    if not math.isfinite(actual) or abs(actual - expected) > 0.005:
        raise ValueError(
            f'A szerződésen kívüli bónusz eltér a havi forrástól '
            f'({actual} / {expected} Ft). A hibás pénzügyi mentés leállítva.'
        )
