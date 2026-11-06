"""Normalize nullable identifiers arriving through pandas request tables."""

from uuid import UUID


def salary_advance_optional_text(value):
    text = str(value).strip()
    return "" if text.casefold() in {"", "none", "null", "nan", "nat", "<na>"} else text


def salary_advance_uuid(value, *, required=False, label="Előlegterv azonosítója"):
    text = salary_advance_optional_text(value)
    if not text:
        if required:
            raise ValueError(f"{label}: hiányzó azonosító.")
        return ""
    try:
        return str(UUID(text))
    except (ValueError, AttributeError):
        raise ValueError(f"{label}: hibás UUID-azonosító. A művelet nem indult el.") from None
