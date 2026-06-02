import io
import unicodedata
import textwrap
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# ── Constants ─────────────────────────────────────────────────────────────────
LOGO_PATH = "assets/logo.png"
STUDIO_NAME = "Your Studio Name"
STUDIO_ADDRESS = "123 Example Street, Singapore 123456"
STUDIO_CONTACT = "hello@yourstudio.com | +65 9000 0000"

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm
TABLE_LEFT = MARGIN
TABLE_RIGHT = PAGE_W - MARGIN
TABLE_WIDTH = TABLE_RIGHT - TABLE_LEFT

COL_WIDTHS = {
    "date":     18 * mm,
    "start":    12 * mm,
    "end":      12 * mm,
    "duration": 12 * mm,
    "game":     50 * mm,
    "type":     20 * mm,
    "room":     12 * mm,
    "fee":      12 * mm,
}

# Additional fees table column widths
EXTRA_COL_WIDTHS = {
    "type":   50 * mm,
    "amount": 30 * mm,
    "notes":  TABLE_WIDTH - 50 * mm - 30 * mm,
}

ROW_HEIGHT   = 7 * mm
HEADER_HEIGHT = 8 * mm
FOOTER_SPACE = 30 * mm

PERIOD_FEES = {
    "Off-peak":   10,
    "M-Th-night": 20,
    "Peak":       30,
    "Special":     0,
}

GAME_NAME_MAX = 40


# ── Helpers ───────────────────────────────────────────────────────────────────
def sanitise_filename(name: str) -> str:
    normalised = unicodedata.normalize("NFKD", name)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in ascii_only.replace(" ", "_"))
    return safe.strip("_")


def _truncate_game(name: str) -> str:
    if len(name) > GAME_NAME_MAX:
        return name[:GAME_NAME_MAX] + "…"
    return name


# ── Canvas helpers ────────────────────────────────────────────────────────────
def _draw_letterhead(c: canvas.Canvas, page_num: int) -> float:
    y = PAGE_H - MARGIN
    logo_h, logo_w = 15 * mm, 40 * mm
    try:
        c.drawImage(LOGO_PATH, MARGIN, y - logo_h, width=logo_w, height=logo_h,
                    preserveAspectRatio=True, mask="auto")
    except Exception:
        pass

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(PAGE_W / 2, y - 8 * mm, STUDIO_NAME)
    c.setFont("Helvetica", 8)
    c.drawCentredString(PAGE_W / 2, y - 13 * mm, STUDIO_ADDRESS)
    c.drawCentredString(PAGE_W / 2, y - 17 * mm, STUDIO_CONTACT)

    divider_y = y - 20 * mm
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.line(MARGIN, divider_y, PAGE_W - MARGIN, divider_y)

    if page_num > 1:
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColor(colors.grey)
        c.drawRightString(PAGE_W - MARGIN, divider_y - 4 * mm, f"(continued — page {page_num})")
        c.setFillColor(colors.black)

    return divider_y - 8 * mm


def _draw_invoice_meta(c: canvas.Canvas, employee: str, month_name: str, year: int, y: float) -> float:
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, f"Invoice for: {employee}")
    c.setFont("Helvetica", 10)
    c.drawRightString(PAGE_W - MARGIN, y, f"Period: {month_name} {year}")
    return y - 10 * mm


def _draw_final_amount_table(
    c: canvas.Canvas,
    y: float,
    session_fee: float,
    extra_fees: list[dict],
) -> float:
    """
    Draw the Final Amount summary table.
    Only called when there are extra fees/credits.
    Rows: Final Amount, Session Fees, then each fee/credit line item.
    """
    fee_items    = [e for e in extra_fees if e["type"] != "Credit"]
    credit_items = [e for e in extra_fees if e["type"] == "Credit"]
    total_fees   = sum(e["amount"] for e in fee_items)
    total_credits= sum(e["amount"] for e in credit_items)
    final_amount = session_fee + total_fees - total_credits

    row_h  = 6 * mm
    col_w1 = 100 * mm
    col_w2 = 40 * mm
    table_w = col_w1 + col_w2

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.black)
    c.drawString(MARGIN, y, "Invoice Total")
    y -= 6 * mm

    def _header_row(label1, label2):
        nonlocal y
        c.setFillColor(colors.HexColor("#222222"))
        c.rect(MARGIN, y - row_h, table_w, row_h, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(MARGIN + 2 * mm, y - row_h + 2 * mm, label1)
        c.drawString(MARGIN + col_w1 + 2 * mm, y - row_h + 2 * mm, label2)
        c.setFillColor(colors.black)
        y -= row_h

    def _data_row(label, amount_str, shade):
        nonlocal y
        if shade:
            c.setFillColor(colors.HexColor("#F5F5F5"))
            c.rect(MARGIN, y - row_h, table_w, row_h, fill=1, stroke=0)
            c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN + 2 * mm, y - row_h + 2 * mm, label)
        c.drawString(MARGIN + col_w1 + 2 * mm, y - row_h + 2 * mm, amount_str)
        c.setStrokeColor(colors.HexColor("#DDDDDD"))
        c.line(MARGIN, y - row_h, MARGIN + table_w, y - row_h)
        c.setStrokeColor(colors.black)
        y -= row_h

    def _total_row(label, amount_str):
        nonlocal y
        c.setFillColor(colors.HexColor("#2A2A2A"))
        c.rect(MARGIN, y - row_h, table_w, row_h, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(MARGIN + 2 * mm, y - row_h + 2 * mm, label)
        c.drawString(MARGIN + col_w1 + 2 * mm, y - row_h + 2 * mm, amount_str)
        c.setFillColor(colors.black)
        y -= row_h

    _header_row("Description", "Amount")
    _total_row("Final Amount", f"${final_amount:.2f}")
    _data_row("Session Fees", f"${session_fee:.2f}", shade=False)

    for i, e in enumerate(fee_items):
        _data_row(e["type"], f"${e['amount']:.2f}", shade=(i % 2 == 0))

    for i, e in enumerate(credit_items):
        _data_row(f"Credit", f"-${e['amount']:.2f}", shade=(i % 2 == 0))

    y -= 6 * mm
    return y


def _draw_employee_notes(c: canvas.Canvas, y: float, notes: str) -> float:
    """Draw employee notes block. Returns new Y."""
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, y, "Notes")
    y -= 5 * mm

    c.setFont("Helvetica", 9)

    max_chars = 90

    # Preserve user-entered line breaks
    paragraphs = notes.splitlines() or [""]

    for paragraph in paragraphs:
        if paragraph.strip():
            wrapped_lines = textwrap.wrap(paragraph, width=max_chars)
            for line in wrapped_lines:
                c.drawString(MARGIN, y, line)
                y -= 4.5 * mm
        else:
            # Blank line in original text
            y -= 4.5 * mm

    y -= 4 * mm
    return y


def _draw_period_summary(c: canvas.Canvas, sessions_df: pd.DataFrame, y: float) -> float:
    periods = ["Off-peak", "M-Th-night", "Peak", "Special"]
    row_h   = 6 * mm
    col_w   = 35 * mm
    table_w = col_w * 4

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.black)
    c.drawString(MARGIN, y, "Summary")
    y -= 6 * mm

    c.setFillColor(colors.HexColor("#222222"))
    c.rect(MARGIN, y - row_h, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    for i, label in enumerate(["Period", "Count", "Rate", "Total"]):
        c.drawString(MARGIN + col_w * i + 2 * mm, y - row_h + 2 * mm, label)
    c.setFillColor(colors.black)
    y -= row_h

    grand_total = 0
    for i, period in enumerate(periods):
        period_rows = sessions_df[sessions_df["period"] == period]
        count = len(period_rows)
        rate  = PERIOD_FEES[period]
        total = period_rows["fee"].sum()
        grand_total += total

        if i % 2 == 0:
            c.setFillColor(colors.HexColor("#F5F5F5"))
            c.rect(MARGIN, y - row_h, table_w, row_h, fill=1, stroke=0)
            c.setFillColor(colors.black)

        c.setFont("Helvetica", 8)
        rate_str = f"${rate:.2f}" if period != "Special" else "varies"
        for j, val in enumerate([period, str(count), rate_str, f"${total:.2f}"]):
            c.drawString(MARGIN + col_w * j + 2 * mm, y - row_h + 2 * mm, val)

        c.setStrokeColor(colors.HexColor("#DDDDDD"))
        c.line(MARGIN, y - row_h, MARGIN + table_w, y - row_h)
        c.setStrokeColor(colors.black)
        y -= row_h

    c.setFillColor(colors.HexColor("#363636"))
    c.rect(MARGIN, y - row_h, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(MARGIN + 2 * mm, y - row_h + 2 * mm, "Session Fees:")
    c.drawString(MARGIN + col_w * 3 + 2 * mm, y - row_h + 2 * mm, f"${grand_total:.2f}")
    c.setFillColor(colors.black)
    y -= row_h

    c.setFont("Helvetica-Oblique", 7)
    c.setFillColor(colors.grey)
    c.drawString(MARGIN, y - 4 * mm, "Note: Special period sessions are invoiced at a manually agreed rate.")
    c.setFillColor(colors.black)
    y -= 10 * mm

    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN, y, "Session Details")
    y -= 6 * mm

    return y


def _draw_extra_fees_table(c: canvas.Canvas, y: float, extra_fees: list[dict]) -> float:
    """Draw the Additional Fees/Credits table. Returns new Y."""
    row_h   = 6 * mm
    table_w = TABLE_WIDTH

    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.black)
    c.drawString(MARGIN, y, "Additional Fees/Credits")
    y -= 6 * mm

    # Header
    c.setFillColor(colors.HexColor("#222222"))
    c.rect(TABLE_LEFT, y - row_h, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    x = TABLE_LEFT + 2 * mm
    for key, label in [("type", "Fee/Credit Type"), ("amount", "Amount ($)"), ("notes", "Notes")]:
        c.drawString(x, y - row_h + 2 * mm, label)
        x += EXTRA_COL_WIDTHS[key]
    c.setFillColor(colors.black)
    y -= row_h

    for i, entry in enumerate(extra_fees):
        if i % 2 == 0:
            c.setFillColor(colors.HexColor("#F5F5F5"))
            c.rect(TABLE_LEFT, y - row_h, table_w, row_h, fill=1, stroke=0)
            c.setFillColor(colors.black)

        c.setFont("Helvetica", 8)
        x = TABLE_LEFT + 2 * mm
        amount_str = f"-${entry['amount']:.2f}" if entry["type"] == "Credit" else f"${entry['amount']:.2f}"
        for key, val in [("type", entry["type"]), ("amount", amount_str), ("notes", entry["notes"])]:
            c.drawString(x, y - row_h + 2 * mm, str(val))
            x += EXTRA_COL_WIDTHS[key]

        c.setStrokeColor(colors.HexColor("#DDDDDD"))
        c.line(TABLE_LEFT, y - row_h, TABLE_RIGHT, y - row_h)
        c.setStrokeColor(colors.black)
        y -= row_h

    y -= 6 * mm
    return y


def _draw_table_header(c: canvas.Canvas, y: float) -> float:
    c.setFillColor(colors.HexColor("#222222"))
    c.rect(TABLE_LEFT, y - HEADER_HEIGHT, TABLE_WIDTH, HEADER_HEIGHT, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    headers = ["Date", "Start", "End", "Duration", "Game", "Type", "Room", "Fee"]
    keys    = ["date", "start", "end", "duration", "game", "type", "room", "fee"]
    x = TABLE_LEFT + 2 * mm
    for key, label in zip(keys, headers):
        c.drawString(x, y - HEADER_HEIGHT + 2 * mm, label)
        x += COL_WIDTHS[key]
    c.setFillColor(colors.black)
    return y - HEADER_HEIGHT


def _draw_row(c: canvas.Canvas, row: pd.Series, y: float, shade: bool) -> float:
    if shade:
        c.setFillColor(colors.HexColor("#F5F5F5"))
        c.rect(TABLE_LEFT, y - ROW_HEIGHT, TABLE_WIDTH, ROW_HEIGHT, fill=1, stroke=0)
        c.setFillColor(colors.black)

    c.setFont("Helvetica", 8)
    x = TABLE_LEFT + 2 * mm
    values = [
        row["start"].strftime("%d %b"),
        row["start"].strftime("%H:%M"),
        row["end"].strftime("%H:%M"),
        f"{row['duration_hours']:.2f}h",
        _truncate_game(str(row["game"])),
        str(row["type"]),
        str(row["room"]),
        f"${row['fee']:.2f}",
    ]
    keys = ["date", "start", "end", "duration", "game", "type", "room", "fee"]
    for key, val in zip(keys, values):
        c.drawString(x, y - ROW_HEIGHT + 2 * mm, val)
        x += COL_WIDTHS[key]

    c.setStrokeColor(colors.HexColor("#DDDDDD"))
    c.line(TABLE_LEFT, y - ROW_HEIGHT, TABLE_RIGHT, y - ROW_HEIGHT)
    c.setStrokeColor(colors.black)
    return y - ROW_HEIGHT


def _draw_totals(c: canvas.Canvas, y: float, total_fee: float) -> None:
    y -= 4 * mm
    c.setStrokeColor(colors.HexColor("#CCCCCC"))
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(PAGE_W - MARGIN, y, f"Session Fees: ${total_fee:.2f}")


# ── Main entry point ──────────────────────────────────────────────────────────
def generate_invoice(
    employee: str,
    sessions_df: pd.DataFrame,
    month_name: str,
    year: int,
    extra_fees: list[dict] | None = None,
    employee_notes: str = "",
) -> bytes:
    if extra_fees is None:
        extra_fees = []

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    sessions_df  = sessions_df.sort_values("start").reset_index(drop=True)
    session_fee  = sessions_df["fee"].sum()
    has_extras   = len(extra_fees) > 0
    has_notes    = bool(employee_notes.strip())

    page_num = 1
    y = _draw_letterhead(c, page_num)
    y = _draw_invoice_meta(c, employee, month_name, year, y)

    # Final amount table (only if there are extra fees/credits)
    if has_extras:
        y = _draw_final_amount_table(c, y, session_fee, extra_fees)

    # Employee notes (only if present)
    if has_notes:
        y = _draw_employee_notes(c, y, employee_notes)

    y = _draw_period_summary(c, sessions_df, y)

    # Additional fees/credits table (only if present)
    if has_extras:
        y = _draw_extra_fees_table(c, y, extra_fees)

    y = _draw_table_header(c, y)

    for i, row in sessions_df.iterrows():
        is_last      = (i == len(sessions_df) - 1)
        space_needed = ROW_HEIGHT + (FOOTER_SPACE if is_last else 0)

        if y - space_needed < MARGIN:
            c.showPage()
            page_num += 1
            y = _draw_letterhead(c, page_num)
            y = _draw_table_header(c, y)

        y = _draw_row(c, row, y, shade=(i % 2 == 0))

    _draw_totals(c, y, session_fee)

    c.save()
    buffer.seek(0)
    return buffer.read()