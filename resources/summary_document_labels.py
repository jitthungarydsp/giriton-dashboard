"""Public document names, including previously saved notification templates.

The legacy internal document type remains ``tig`` for stored record compatibility.
"""
import re

DOCUMENT_NAME = "Teljesítés-összesítő"


def summary_document_text(value: object) -> str:
    text = str(value or "")
    endings = {"et": "t", "ed": "d", "re": "re", "ben": "ben", "ből": "ből",
               "hez": "höz", "nél": "nél", "nek": "nek", "ek": "k"}
    text = re.sub(r"\bTIG-(et|ed|re|ben|ből|hez|nél|nek|ek)\b",
                  lambda match: DOCUMENT_NAME + endings[match[1]], text)
    text = re.sub(r"\bTIG\b", DOCUMENT_NAME, text)
    return re.sub(r"teljesítési igazolás", DOCUMENT_NAME, text, flags=re.IGNORECASE)
