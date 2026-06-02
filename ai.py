import os
import calendar
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ── AI Report Instructions ────────────────────────────────────────────────────
SYSTEM_CONTEXT = """
You are Lorelei, an internal analytics assistant for a game studio manager reviewing monthly venue rental data.

Your job is NOT to calculate metrics from raw data. Python has already calculated the metrics.
Your job is to turn the provided data summary into a concise, accurate, manager-friendly report.

Important constraints:
- Do not invent causes.
- Do not refer to metrics not provided.
- Use only the numbers in the data summary.
- Frame recommendations as follow-up actions, not conclusions.
- Keep the report concise and useful for a manager.
- Highlight patterns, risks, and next-step recommendations.
- Ignore extra fees, credits, and employee notes. This report is based only on session data and session fees.

You must output only these sections:

LORELEI'S MONTHLY ANALYTICS SUMMARY

**1. Executive Summary**
- Bullet points only.

**2. Top Performers**
- Top employees.
- Top game names.

**3. Period Mix**
- Off-peak / M-Th-night / Peak / Special.

**4. Underutilized Days**
- Low session days.
- Low revenue days.

**5. Manager Recommendations**
- Write this as a short prioritized narrative in bullet points.
- Recommendations should be practical follow-up actions, not definitive conclusions.

Add this final signature:
Keep playing your stories! Love, Lorelei
"""


def _format_money(value: float) -> str:
    """Format a number as money with two decimal places."""
    return f"${value:,.2f}"


def _safe_date(value) -> str:
    """Convert a date-like value into a readable date string."""
    try:
        return pd.to_datetime(value).strftime("%d %b %Y")
    except Exception:
        return str(value)


def _filter_valid_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return only valid rows if a valid column exists."""
    df = df.copy()

    if "valid" in df.columns:
        df = df[df["valid"] == True].copy()

    return df


def _prepare_session_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert start values into datetime values for date-based analysis."""
    df = df.copy()
    df["start"] = pd.to_datetime(df["start"], errors="coerce")

    try:
        if df["start"].dt.tz is not None:
            df["start"] = df["start"].dt.tz_localize(None)
    except Exception:
        pass

    return df


def _add_basic_totals(lines: list[str], df: pd.DataFrame, month_name: str, year: int) -> None:
    """Add month, total sessions, and total session fees to the summary."""
    total_sessions = len(df)
    total_session_fees = df["fee"].sum() if "fee" in df.columns else 0

    lines.append(f"Month: {month_name} {year}")
    lines.append(f"Total sessions: {total_sessions}")
    lines.append(f"Total session fees: {_format_money(total_session_fees)}")


def _add_top_employees(lines: list[str], df: pd.DataFrame) -> None:
    """Add the top three employees by session count to the summary."""
    lines.append("\nTop 3 busiest employees by session count:")

    if df.empty:
        lines.append("  - No session data available.")
        return

    top_employees = (
        df.groupby("name")
        .agg(
            sessions=("fee", "count"),
            total_session_fees=("fee", "sum"),
        )
        .reset_index()
        .sort_values(
            by=["sessions", "total_session_fees", "name"],
            ascending=[False, False, True],
        )
        .head(3)
    )

    for _, row in top_employees.iterrows():
        lines.append(
            f"  - {row['name']}: "
            f"{int(row['sessions'])} session(s), "
            f"{_format_money(row['total_session_fees'])} session fees"
        )


def _add_top_games(lines: list[str], df: pd.DataFrame) -> None:
    """Add the top three games by session count to the summary."""
    lines.append("\nTop 3 game names by session count:")

    if df.empty:
        lines.append("  - No game data available.")
        return

    top_games = (
        df.groupby("game")
        .agg(
            sessions=("fee", "count"),
            total_session_fees=("fee", "sum"),
        )
        .reset_index()
        .sort_values(
            by=["sessions", "total_session_fees", "game"],
            ascending=[False, False, True],
        )
        .head(3)
    )

    for _, row in top_games.iterrows():
        lines.append(
            f"  - {row['game']}: "
            f"{int(row['sessions'])} session(s), "
            f"{_format_money(row['total_session_fees'])} session fees"
        )


def _add_period_counts(lines: list[str], df: pd.DataFrame) -> None:
    """Add session counts by period to the summary."""
    lines.append("\nSession count by period:")

    period_order = ["Off-peak", "M-Th-night", "Peak", "Special"]
    period_counts = df["period"].value_counts().to_dict() if "period" in df.columns else {}

    for period in period_order:
        lines.append(f"  - {period}: {int(period_counts.get(period, 0))} session(s)")

    unexpected_periods = sorted(
        period for period in period_counts.keys()
        if period not in period_order
    )

    for period in unexpected_periods:
        lines.append(f"  - {period}: {int(period_counts.get(period, 0))} session(s)")


def _build_daily_summary(df: pd.DataFrame, month_name: str, year: int) -> pd.DataFrame:
    """Build a daily summary that includes days with zero sessions."""
    month_number = list(calendar.month_name).index(month_name)
    days_in_month = calendar.monthrange(year, month_number)[1]

    all_dates = pd.date_range(
        start=f"{year}-{month_number:02d}-01",
        end=f"{year}-{month_number:02d}-{days_in_month}",
        freq="D",
    )

    df = df.copy()
    df["session_date"] = df["start"].dt.normalize()

    daily = (
        df.groupby("session_date")
        .agg(
            sessions=("fee", "count"),
            session_fees=("fee", "sum"),
        )
        .reindex(all_dates, fill_value=0)
        .reset_index()
        .rename(columns={"index": "date"})
    )

    return daily


def _add_underutilized_days(lines: list[str], daily: pd.DataFrame) -> None:
    """Add low-session and low-revenue days to the summary."""
    low_session_days = daily[daily["sessions"] <= 1].copy()
    low_revenue_days = daily[daily["session_fees"] <= 20].copy()

    lines.append("\nUnderutilized days by session count:")
    lines.append("Definition: days with 1 or fewer sessions.")

    if low_session_days.empty:
        lines.append("  - None.")
    else:
        for _, row in low_session_days.iterrows():
            lines.append(
                f"  - {_safe_date(row['date'])}: "
                f"{int(row['sessions'])} session(s), "
                f"{_format_money(row['session_fees'])} session fees"
            )

    lines.append("\nUnderutilized days by revenue:")
    lines.append("Definition: days with $20.00 or less in session fees.")

    if low_revenue_days.empty:
        lines.append("  - None.")
    else:
        for _, row in low_revenue_days.iterrows():
            lines.append(
                f"  - {_safe_date(row['date'])}: "
                f"{int(row['sessions'])} session(s), "
                f"{_format_money(row['session_fees'])} session fees"
            )


def _build_data_summary(df: pd.DataFrame, month_name: str, year: int) -> str:
    """Build a compact Python-calculated analytics summary for the AI report."""
    required_columns = ["name", "game", "start", "period", "fee"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        return (
            "ERROR: The report could not be generated because the uploaded data is missing "
            f"these required column(s): {', '.join(missing_columns)}."
        )

    df = _filter_valid_rows(df)
    df = _prepare_session_dates(df)

    lines = []

    _add_basic_totals(lines, df, month_name, year)
    _add_top_employees(lines, df)
    _add_top_games(lines, df)
    _add_period_counts(lines, df)

    daily = _build_daily_summary(df, month_name, year)
    _add_underutilized_days(lines, daily)

    return "\n".join(lines)


def _call_ai_report(data_summary: str) -> str:
    """Call the OpenAI model and return the generated analytics report."""
    if data_summary.startswith("ERROR:"):
        return data_summary

    if not os.getenv("OPENAI_API_KEY"):
        return (
            "AI report could not be generated because OPENAI_API_KEY is missing. "
            "Please add your API key to the .env file and try again."
        )

    try:
        response = client.responses.create(
            model="gpt-5-mini",
            input=[
                {
                    "role": "system",
                    "content": SYSTEM_CONTEXT,
                },
                {
                    "role": "user",
                    "content": (
                        "Here is the Python-calculated data summary:\n\n"
                        f"{data_summary}\n\n"
                        "Write the report now using only the data above."
                    ),
                },
            ],
        )

        report_text = getattr(response, "output_text", "")

        if not report_text or not report_text.strip():
            return (
                "AI report could not be generated because the API returned an empty response. "
                "Please try again."
            )

        return report_text.strip()

    except Exception as error:
        return (
            "AI report could not be generated because the API call failed. "
            f"Details: {error}"
        )


def get_ai_summary(df: pd.DataFrame, month_name: str, year: int) -> str:
    """Generate a concise manager-friendly AI report from monthly session data."""
    data_summary = _build_data_summary(df, month_name, year)
    return _call_ai_report(data_summary)


def prepare_report_download(report_text: str, month_name: str, year: int) -> tuple[str, str]:
    """Prepare the filename and text content for downloading the AI report."""
    safe_month = str(month_name).strip().replace(" ", "_")
    filename = f"lorelei_report_{safe_month}_{year}.txt"

    if not report_text or not report_text.strip():
        report_text = "No report text was available to download."

    return filename, report_text