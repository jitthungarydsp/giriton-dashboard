"""Identify the workbook's separately supplied out-of-contract bonuses."""
import re
import unicodedata

BONUS_LABEL = "Szerződésen kívüli bónusz"
BONUS_SOURCE = "Out_of_contract_Bonus Routes"


def is_out_of_contract_bonus_sheet(value: object) -> bool:
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', text) in {
        'outofcontractbonusroutes', 'outofcontractbonusroute', 'outofcontractbonus',
    }
