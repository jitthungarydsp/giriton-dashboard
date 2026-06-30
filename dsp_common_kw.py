from datetime import datetime
from zoneinfo import ZoneInfo

LOCAL_TIMEZONE = ZoneInfo("Europe/Budapest")


def local_now():
    return datetime.now(LOCAL_TIMEZONE)


def local_today():
    return local_now().date()


def parse_datetime(value):
    if not value:
        return None

    text = str(value).strip()

    if not text:
        return None

    for date_format in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    ]:
        try:
            parsed = datetime.strptime(text, date_format)
            return parsed.replace(tzinfo=LOCAL_TIMEZONE)
        except ValueError:
            pass

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)

        return parsed.astimezone(LOCAL_TIMEZONE)
    except ValueError:
        return None


def hu_time(value):

    if not value:
        return ""

    dt = parse_datetime(value)

    if not dt:
        return str(value)

    return dt.astimezone(
        LOCAL_TIMEZONE
    ).strftime("%Y-%m-%d %H:%M:%S")
