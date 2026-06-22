from datetime import datetime
from zoneinfo import ZoneInfo

def hu_time(value):

    if not value:
        return ""

    dt = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )

    return dt.astimezone(
        ZoneInfo("Europe/Budapest")
    ).strftime("%Y-%m-%d %H:%M:%S")