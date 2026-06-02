import pandas as pd
from datetime import time

VALID_TYPES = {"Flash", "Voyage", "Saga", "Other", "Empty"}

# ── Period definitions ────────────────────────────────────────────────────────
# Each period is a tuple of:
#   (name, days, core_start, core_end)
# days: set of weekday integers (0=Mon, 6=Sun)
# core_start / core_end: time objects for the core window (before tolerance)

PERIODS = [
    ("Off-peak",   {0, 1, 2, 3, 4}, time(8,  0), time(12, 0)),  # Mon-Fri 8am-12pm
    ("Off-peak",   {0, 1, 2, 3, 4}, time(13, 0), time(17, 0)),  # Mon-Fri 1pm-5pm
    ("M-Th-night", {0, 1, 2, 3},    time(18, 0), time(22, 0)),  # Mon-Thu 6pm-10pm
    ("Peak",       {4},             time(18, 0), time(22, 0)),  # Fri 6pm-10pm
    ("Peak",       {5, 6},          time(8,  0), time(12, 0)),  # Sat-Sun 8am-12pm
    ("Peak",       {5, 6},          time(13, 0), time(17, 0)),  # Sat-Sun 1pm-5pm
    ("Peak",       {5, 6},          time(18, 0), time(22, 0)),  # Sat-Sun 6pm-10pm
]

PERIOD_FEES = {
    "Off-peak":   10.00,
    "M-Th-night": 20.00,
    "Peak":       30.00,
    "Special":     0.00,
}


def _fits_period(s_time: time, e_time: time, weekday: int,
                 days: set, core_start: time, core_end: time) -> bool:
    """
    Return True if a block (s_time, e_time) on a given weekday fits within
    the padded window of a period (core ± 1 hour on each side).

    Padded window check:
      S >= core_start - 1hr  AND  S <= core_end
      E >= core_start        AND  E <= core_end + 1hr
    """
    from datetime import datetime, timedelta

    if weekday not in days:
        return False

    base = datetime(2000, 1, 1)
    cs = datetime.combine(base.date(), core_start)
    ce = datetime.combine(base.date(), core_end)
    s  = datetime.combine(base.date(), s_time)
    e  = datetime.combine(base.date(), e_time)

    padded_start = cs - timedelta(hours=1)
    padded_end   = ce + timedelta(hours=1)

    s_ok = (s >= padded_start) and (s <= ce)
    e_ok = (e >= cs)           and (e <= padded_end)

    return s_ok and e_ok


def assign_period(start, end) -> str:
    """
    Assign a period tag to a session given its start and end datetimes.
    Returns one of: "Off-peak", "M-Th-night", "Peak", "Special".
    """
    s_time  = start.time().replace(second=0, microsecond=0)
    e_time  = end.time().replace(second=0, microsecond=0)
    weekday = start.weekday()  # 0=Mon, 6=Sun

    matches = []
    for (period_name, days, core_start, core_end) in PERIODS:
        if _fits_period(s_time, e_time, weekday, days, core_start, core_end):
            matches.append(period_name)

    if len(matches) == 1:
        return matches[0]
    else:
        return "Special"


def _build_issues(row) -> list[str]:
    """
    Run all validation rules on a single row and return a list of issue strings.
    Does NOT assign or check period — period is assumed already set in row["period"].
    """
    issues = []

    # Rule 1: field count
    if row["field_count"] < 2 or row["field_count"] > 3:
        issues.append(f"Expected 2 or 3 fields, found {row['field_count']}")

    # Rule 2: duration
    if row["duration_hours"] <= 0:
        issues.append("Duration is zero or negative")

    # Rule 3: name must be a single word
    name = str(row["name"]).strip()
    if " " in name or not name:
        issues.append(f"Name '{name}' must be a single word with no spaces")

    # Rule 4: type validity
    entry_type = str(row["type"]).strip()
    if entry_type not in VALID_TYPES:
        issues.append(f"Type '{entry_type}' not recognised — expected Flash, Voyage, Saga, Other, or Empty")

    # Rule 5: Special period requires manual fee review
    if row["period"] == "Special":
        issues.append("Special period — review and set fee manually")

    return issues


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Full validation for initial load.
    Assigns period from start/end times, then runs all issue checks.
    Adds columns: 'period', 'issues', 'valid'.
    """
    df = df.copy()
    df["period"] = df.apply(lambda r: assign_period(r["start"], r["end"]), axis=1)

    df["issues"] = df.apply(_build_issues, axis=1)
    df["valid"]  = df["issues"].apply(lambda x: len(x) == 0)

    return df


def revalidate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validation for rows that have already been through the fix editor.
    Trusts whatever is already in df["period"] — does NOT call assign_period.
    Re-runs all issue checks and updates 'issues' and 'valid'.
    """
    df = df.copy()
    df["issues"] = df.apply(_build_issues, axis=1)
    df["valid"]  = df["issues"].apply(lambda x: len(x) == 0)

    return df


def split_by_validity(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean_df, flagged_df) as separate dataframes."""
    clean   = df[df["valid"]].reset_index(drop=True)
    flagged = df[~df["valid"]].reset_index(drop=True)
    return clean, flagged