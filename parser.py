import hashlib
import zoneinfo
import calendar as cal_module
import datetime
from icalendar import Calendar
import recurring_ical_events
import pandas as pd

SGT = zoneinfo.ZoneInfo("Asia/Singapore")


def hash_file(file_bytes: bytes) -> str:
    """Return MD5 hash of file bytes."""
    return hashlib.md5(file_bytes).hexdigest()


def files_are_identical(file1_bytes: bytes, file2_bytes: bytes) -> bool:
    """Return True if both uploaded files are the same."""
    return hash_file(file1_bytes) == hash_file(file2_bytes)


def parse_ics(file_bytes: bytes, room_label: str, month: int, year: int) -> list[dict]:
    """
    Parse an .ics file and return session dicts for the chosen month/year.
    Uses recurring_ical_events to correctly expand recurring events.
    Skips: cancelled events and all-day events.
    """
    cal = Calendar.from_ical(file_bytes)

    # Build a SGT-aware date range covering the full selected month
    first_day = datetime.datetime(year, month, 1, tzinfo=SGT)
    last_day  = datetime.datetime(
        year, month, cal_module.monthrange(year, month)[1],
        23, 59, 59, tzinfo=SGT
    )

    events = recurring_ical_events.of(cal).between(first_day, last_day)
    sessions = []

    for component in events:
        # Skip cancelled events
        status = str(component.get("STATUS", "")).upper()
        if status == "CANCELLED":
            continue

        dtstart = component.get("DTSTART")
        dtend   = component.get("DTEND")
        summary = str(component.get("SUMMARY", "")).strip()

        if not summary or not dtstart or not dtend:
            continue

        start = dtstart.dt
        end   = dtend.dt

        # Skip all-day events (date only, no time component)
        if not hasattr(start, "hour"):
            continue

        # Normalise naive datetimes to UTC then convert to SGT
        if start.tzinfo is None:
            start = start.replace(tzinfo=datetime.timezone.utc)
            end   = end.replace(tzinfo=datetime.timezone.utc)

        start_local = start.astimezone(SGT)
        end_local   = end.astimezone(SGT)

        duration_hours = round(
            (end_local - start_local).total_seconds() / 3600, 2
        )

        sessions.append({
            "raw_title":      summary,
            "start":          start_local,
            "end":            end_local,
            "duration_hours": duration_hours,
            "room":           room_label,
        })

    return sessions


def split_and_clean(sessions: list[dict]) -> pd.DataFrame:
    """
    Expect title format: "Name, Game Name, Type"
    Also handles 2-field format: "Name, Game Name" — type is set to "Empty".
    Split on comma, strip whitespace. Store field_count for validator.
    """
    rows = []
    for s in sessions:
        parts       = [p.strip() for p in s["raw_title"].split(",")]
        field_count = len(parts)

        if field_count == 2:
            type_value = "Empty"
        else:
            type_value = parts[2] if field_count > 2 else ""

        rows.append({
            "name":           parts[0] if field_count > 0 else "",
            "game":           parts[1] if field_count > 1 else "",
            "type":           type_value,
            "start":          s["start"],
            "end":            s["end"],
            "duration_hours": s["duration_hours"],
            "room":           s["room"],
            "raw_title":      s["raw_title"],
            "field_count":    field_count,
        })

    return pd.DataFrame(rows)