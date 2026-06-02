import streamlit as st
import pandas as pd
from datetime import datetime
import zipfile
import io
from itertools import combinations

from parser import files_are_identical, parse_ics, split_and_clean
from validator import validate, revalidate, PERIOD_FEES
from invoice import generate_invoice
from ai import get_ai_summary, prepare_report_download

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Lorelei: Studio Invoice Generator", layout="wide")

title_img_col, title_text_col = st.columns([1, 10], vertical_alignment="center")
with title_img_col:
    st.image("assets/lorelei.png", width=200)
with title_text_col:
    st.title("Lorelei: Studio Invoice Generator")

st.markdown("""
    <style>
    [data-testid="stDataFrame"] > div {
        overflow-x: auto !important;
    }
    </style>
""", unsafe_allow_html=True)

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
YEARS = list(range(2023, 2054))
FEE_CREDIT_TYPES = ["Marketing Fee", "Art Fee", "Other Fee", "Credit"]
ROOM_LABELS = ["Room 1", "Room 2", "Room 3", "Room 4"]

# ── Step 1: Month / Year selector ─────────────────────────────────────────────
st.header("Step 1: Select Month & Year")
col1, col2 = st.columns(2)
with col1:
    selected_month_name = st.selectbox("Month", MONTHS, index=datetime.now().month - 1)
with col2:
    selected_year = st.selectbox("Year", YEARS, index=YEARS.index(datetime.now().year))

selected_month = MONTHS.index(selected_month_name) + 1

# ── Step 2: File upload ────────────────────────────────────────────────────────
st.header("Step 2: Upload Calendar Files")
st.caption(
    "For each calendar, go to ⚙️ Settings and sharing → Export calendar. "
    "Upload Room 1's calendar as Room 1, etc. Click Skip for any rooms not in use."
)

if "room_bytes" not in st.session_state:
    st.session_state["room_bytes"] = {label: None for label in ROOM_LABELS}
if "room_skipped" not in st.session_state:
    st.session_state["room_skipped"] = {label: False for label in ROOM_LABELS}

room_bytes = st.session_state["room_bytes"]
room_skipped = st.session_state["room_skipped"]

for label in ROOM_LABELS:
    col_skip, col_upload, _ = st.columns([1, 3, 12], vertical_alignment="center")

    with col_skip:
        if st.button("Skip", key=f"skip_{label}"):
            room_bytes[label] = None
            room_skipped[label] = True

    with col_upload:
        f = st.file_uploader(label, type="ics", key=f"upload_{label}")
        if f is not None:
            room_bytes[label] = f.read()
            room_skipped[label] = False

undecided = [
    label for label in ROOM_LABELS
    if room_bytes[label] is None and not room_skipped[label]
]
if undecided:
    st.info(f"Please upload or skip all rooms to continue. Waiting on: {', '.join(undecided)}.")
    st.stop()

uploaded_rooms = {
    label: room_bytes[label]
    for label in ROOM_LABELS
    if room_bytes[label] is not None
}

if not uploaded_rooms:
    st.error("All rooms were skipped — please upload at least one calendar file.")
    st.stop()

st.success(
    f"{len(uploaded_rooms)} room calendar{'s' if len(uploaded_rooms) != 1 else ''} uploaded: "
    f"{', '.join(uploaded_rooms.keys())}."
)

# ── Identical file check ───────────────────────────────────────────────────────
room_labels_list = list(uploaded_rooms.keys())
room_bytes_list = list(uploaded_rooms.values())

identical_pairs = [
    (room_labels_list[i], room_labels_list[j])
    for i, j in combinations(range(len(room_bytes_list)), 2)
    if files_are_identical(room_bytes_list[i], room_bytes_list[j])
]
if identical_pairs:
    for label_a, label_b in identical_pairs:
        st.error(f"'{label_a}' and '{label_b}' are identical — please check you uploaded the correct files.")
    st.stop()

input_key = (
    f"{selected_month}_{selected_year}_"
    + "_".join(f"{l}:{hash(b)}" for l, b in sorted(uploaded_rooms.items()))
)
if st.session_state.get("input_key") != input_key:
    saved_bytes = st.session_state["room_bytes"].copy()
    saved_skipped = st.session_state["room_skipped"].copy()
    st.session_state.clear()
    st.session_state["input_key"] = input_key
    st.session_state["room_bytes"] = saved_bytes
    st.session_state["room_skipped"] = saved_skipped

# ── Parse and clean ────────────────────────────────────────────────────────────
all_sessions = []
for label, file_bytes in uploaded_rooms.items():
    all_sessions.extend(parse_ics(file_bytes, label, selected_month, selected_year))

all_sessions = sorted(all_sessions, key=lambda s: s["start"])

if not all_sessions:
    st.warning(f"No sessions found for {selected_month_name} {selected_year}. Check your files and selected month.")
    st.stop()

df = split_and_clean(all_sessions)

# ── Initialise session state ───────────────────────────────────────────────────
if "df" not in st.session_state:
    df = validate(df)
    df["fee"] = df["period"].map(PERIOD_FEES).fillna(0)
    df["manually_flagged"] = False
    st.session_state["df"] = df
else:
    df = st.session_state["df"]

if "extra_fees" not in st.session_state:
    st.session_state["extra_fees"] = {}

if "employee_notes" not in st.session_state:
    st.session_state["employee_notes"] = {}

employee_names = sorted(df["name"].unique().tolist())

# ── Step 3: Review Sessions ────────────────────────────────────────────────────
st.header("Step 3: Review Sessions")

st.caption(
    "🔴 Validation error &nbsp;|&nbsp; "
    "🟡 Special period (fee defaults to $0, set manually in Fix section below) &nbsp;|&nbsp; "
    "🔵 Manually selected to be fixed below &nbsp;|&nbsp; "
    "Invoices can still be generated with flagged entries, but review carefully before doing so."
)


def highlight_issues(row):
    """Apply background colors to review rows based on manual flags, validation errors, or Special periods."""
    if row.get("manually_flagged", False):
        return ["background-color: #cce5ff"] * len(row)
    if not row["valid"]:
        if any("Special period" in i for i in row["issues"]):
            return ["background-color: #fff3cd"] * len(row)
        return ["background-color: #ffd6d6"] * len(row)
    return [""] * len(row)


review_cols = [
    "manually_flagged", "name", "game", "type", "period", "start", "end",
    "duration_hours", "room", "fee", "valid", "issues"
]
review_df = df[review_cols].copy()
review_df.index = range(1, len(review_df) + 1)
styled_df = review_df.style.apply(highlight_issues, axis=1)

edited_review = st.data_editor(
    styled_df,
    width="stretch",
    height=400,
    key=f"review_{st.session_state.get('editor_key', 0)}",
    column_config={
        "_index": st.column_config.NumberColumn(width="small"),
        "manually_flagged": st.column_config.CheckboxColumn(
            label="Fix?",
            help="Check to send this row to Fix Flagged Entries",
            default=False,
        ),
        "name": st.column_config.TextColumn(disabled=True),
        "game": st.column_config.TextColumn(disabled=True),
        "type": st.column_config.TextColumn(disabled=True),
        "period": st.column_config.TextColumn(disabled=True),
        "start": st.column_config.DatetimeColumn(disabled=True),
        "end": st.column_config.DatetimeColumn(disabled=True),
        "duration_hours": st.column_config.NumberColumn(disabled=True, format="%.2f"),
        "room": st.column_config.TextColumn(disabled=True),
        "fee": st.column_config.NumberColumn(disabled=True, format="%.2f"),
        "valid": st.column_config.CheckboxColumn(disabled=True),
        "issues": st.column_config.ListColumn(),
    },
)

edited_flags = edited_review["manually_flagged"].values
current_flags = df["manually_flagged"].values
if list(edited_flags) != list(current_flags):
    df["manually_flagged"] = edited_flags
    for idx in df.index:
        if df.at[idx, "manually_flagged"]:
            if "Manually flagged by user" not in df.at[idx, "issues"]:
                df.at[idx, "issues"] = df.at[idx, "issues"] + ["Manually flagged by user"]
            df.at[idx, "valid"] = False
        else:
            df.at[idx, "issues"] = [i for i in df.at[idx, "issues"] if i != "Manually flagged by user"]
            if not df.at[idx, "issues"]:
                df.at[idx, "valid"] = True
    st.session_state["df"] = df
    st.rerun()

# ── Fix flagged entries ────────────────────────────────────────────────────────
needs_fix = df[~df["valid"] | df["manually_flagged"]]
if not needs_fix.empty:
    st.subheader("Fix Flagged Entries")
    st.caption(
        "Edit name, game, type, start, end, room, or period directly. Remember to click Apply Fixes below for changes to take effect! "
        "Changing period overrides the auto-assigned value — set to Special to enable manual fee entry below."
    )

    editable_cols = ["name", "game", "type", "start", "end", "room", "period"]
    flagged_display = df.loc[needs_fix.index, editable_cols].copy()
    flagged_display.index = range(1, len(flagged_display) + 1)

    edited = st.data_editor(
        flagged_display,
        width="stretch",
        height=300,
        key=f"editor_{st.session_state.get('editor_key', 0)}",
        column_config={
            "period": st.column_config.SelectboxColumn(
                label="Period",
                options=["Off-peak", "M-Th-night", "Peak", "Special"],
                required=True,
            ),
        },
    )

    original_indices = needs_fix.index.tolist()
    special_indices = [
        (di, oi) for di, oi in enumerate(original_indices)
        if edited.iloc[di]["period"] == "Special"
    ]

    if special_indices:
        st.caption(
            "💛 Set fees for Special period rows below (default $0 if left blank). "
            "After clicking Apply Fixes, Special period rows will update above but continue to display below so fees can still be adjusted."
        )
        special_fees = {}
        for display_idx, orig_idx in special_indices:
            row = df.loc[orig_idx]
            label = f"{row['name']} — {row['start'].strftime('%d %b %H:%M')} ({row['game']})"
            special_fees[orig_idx] = st.number_input(
                label,
                min_value=0.0,
                value=float(df.at[orig_idx, "fee"]),
                step=5.0,
                format="%.2f",
                key=f"special_fee_{orig_idx}_{st.session_state.get('editor_key', 0)}",
            )

    if st.button("Apply Fixes"):
        for display_idx, orig_idx in enumerate(original_indices):
            row = edited.iloc[display_idx]
            for col in editable_cols:
                df.at[orig_idx, col] = row[col]

        for orig_idx in original_indices:
            df.at[orig_idx, "duration_hours"] = round(
                (df.at[orig_idx, "end"] - df.at[orig_idx, "start"]).total_seconds() / 3600,
                2,
            )
            df.at[orig_idx, "field_count"] = (
                2 if df.at[orig_idx, "type"] in ("", "Empty") else 3
            )

        df["manually_flagged"] = False

        flagged_revalidated = revalidate(df.loc[original_indices].copy())
        df.loc[original_indices, "issues"] = flagged_revalidated["issues"].values
        df.loc[original_indices, "valid"] = flagged_revalidated["valid"].values

        for orig_idx in original_indices:
            df.at[orig_idx, "fee"] = PERIOD_FEES.get(df.at[orig_idx, "period"], 0)

        for display_idx, orig_idx in special_indices:
            if orig_idx in special_fees:
                df.at[orig_idx, "fee"] = special_fees[orig_idx]

        st.session_state["df"] = df
        st.session_state["editor_key"] = st.session_state.get("editor_key", 0) + 1
        st.success("Fixes applied.")
        st.rerun()

# ── Step 4: Additional Fees / Credits ─────────────────────────────────────────
st.header("Step 4: Add Additional Fees/Credits (Optional)")

with st.form("add_fee_form", clear_on_submit=True, enter_to_submit=False):
    col_a, col_b = st.columns(2)
    with col_a:
        fee_employee = st.selectbox("Employee", employee_names, key="fee_emp")
    with col_b:
        fee_type = st.selectbox("Fee/Credit Type", FEE_CREDIT_TYPES, key="fee_type")

    col_c, col_d = st.columns([1, 2])
    with col_c:
        amount_label = "Credit Amount ($)" if fee_type == "Credit" else "Fee Amount ($)"
        fee_amount = st.number_input(
            amount_label,
            min_value=0.0,
            step=5.0,
            format="%.2f",
            key="fee_amount",
        )
    with col_d:
        fee_notes = st.text_input("Notes (optional)", key="fee_notes")

    if st.form_submit_button("Add"):
        entry = {
            "type": fee_type,
            "amount": round(fee_amount, 2),
            "notes": fee_notes.strip() if fee_notes.strip() else "None",
        }
        if fee_employee not in st.session_state["extra_fees"]:
            st.session_state["extra_fees"][fee_employee] = []
        st.session_state["extra_fees"][fee_employee].append(entry)
        st.success(f"Added {fee_type} of ${fee_amount:.2f} for {fee_employee}.")

# ── Step 5: Employee Notes ─────────────────────────────────────────────────────
st.header("Step 5: Add Notes (Optional)")

with st.form("add_notes_form", clear_on_submit=True, enter_to_submit=False):
    notes_employee = st.selectbox("Employee", employee_names, key="notes_emp")
    notes_text = st.text_area("Notes", key="notes_text", height=100)

    if st.form_submit_button("Add Note"):
        if notes_text.strip():
            st.session_state["employee_notes"][notes_employee] = notes_text.strip()
            st.success(f"Note added for {notes_employee}.")
        else:
            st.warning("Notes field is empty — nothing added.")

# ── Step 6: Preview by Employee ───────────────────────────────────────────────
st.header("Step 6: Preview by Employee")

for employee, group in df.groupby("name"):
    session_fee = group["fee"].sum()
    extra = st.session_state["extra_fees"].get(employee, [])
    notes = st.session_state["employee_notes"].get(employee, "")
    total_fees = sum(e["amount"] for e in extra if e["type"] != "Credit")
    total_credits = sum(e["amount"] for e in extra if e["type"] == "Credit")
    final_amount = session_fee + total_fees - total_credits
    has_issues = not group["valid"].all()
    label = f"⚠️ {employee}" if has_issues else employee

    with st.expander(f"{label} — {len(group)} session(s) — Final Total: ${final_amount:.2f}"):

        # ── Notes ─────────────────────────────────────────────────────────────
        if notes:
            st.markdown("**Notes**")

            delete_note = st.checkbox(
                "DELETE? This cannot be undone!",
                key=f"delete_note_{employee}_{st.session_state.get('editor_key', 0)}",
            )

            st.markdown(
                notes.replace("\n", "  \n"),
                unsafe_allow_html=False,
            )

            if delete_note:
                del st.session_state["employee_notes"][employee]
                st.rerun()

        # ── Additional fees/credits ────────────────────────────────────────────
        if extra:
            st.markdown("**Additional Fees/Credits**")
            extra_display = pd.DataFrame([
                {
                    "DELETE? This cannot be undone!": False,
                    "Fee/Credit Type": e["type"],
                    "Amount ($)": e["amount"],
                    "Notes": e["notes"],
                }
                for e in extra
            ])
            extra_display.index = range(1, len(extra_display) + 1)

            edited_extra = st.data_editor(
                extra_display,
                key=f"extra_{employee}_{st.session_state.get('editor_key', 0)}",
                column_config={
                    "DELETE? This cannot be undone!": st.column_config.CheckboxColumn(
                        label="DELETE? This cannot be undone!"
                    ),
                    "Fee/Credit Type": st.column_config.TextColumn(disabled=True),
                    "Amount ($)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
                    "Notes": st.column_config.TextColumn(disabled=True),
                },
                hide_index=False,
                width="stretch",
            )

            to_keep = [
                entry for i, entry in enumerate(extra)
                if not edited_extra.iloc[i]["DELETE? This cannot be undone!"]
            ]
            if len(to_keep) < len(extra):
                st.session_state["extra_fees"][employee] = to_keep
                st.rerun()

        # ── Session fees ───────────────────────────────────────────────────────
        st.markdown("**Session Fees**")
        st.dataframe(
            group[["game", "type", "period", "start", "room", "duration_hours", "fee"]],
            width="stretch",
        )

        if has_issues:
            st.warning("This employee has flagged entries. Review before generating invoices.")

# ── Step 7: Generate Invoices ──────────────────────────────────────────────────
st.header("Step 7: Generate Invoices")

if st.button("Generate All Invoices", type="secondary"):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for employee, group in df.groupby("name"):
            extra = st.session_state["extra_fees"].get(employee, [])
            notes = st.session_state["employee_notes"].get(employee, "")
            pdf_bytes = generate_invoice(
                employee=employee,
                sessions_df=group,
                month_name=selected_month_name,
                year=selected_year,
                extra_fees=extra,
                employee_notes=notes,
            )
            filename = f"Invoice_{selected_month_name}_{selected_year}_{employee}.pdf"
            zf.writestr(filename, pdf_bytes)

    zip_buffer.seek(0)
    st.download_button(
        label="Download All Invoices (.zip)",
        data=zip_buffer,
        file_name=f"Invoices_{selected_month_name}_{selected_year}.zip",
        mime="application/zip",
        type="primary",
    )
    st.success("Invoices generated! Click above to download.")

# ── Downloads ──────────────────────────────────────────────────────────────────
col_dl1, col_dl2 = st.columns(2)

with col_dl1:
    display_cols = [
        "name", "game", "type", "period", "start", "end",
        "duration_hours", "room", "fee", "valid", "issues"
    ]

    sessions_export = df[display_cols].copy()
    sessions_export["Notes"] = sessions_export["name"].map(
        lambda emp: st.session_state["employee_notes"].get(emp, "None")
    )

    csv_bytes = sessions_export.to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download Session (.csv)",
        csv_bytes,
        f"sessions_{selected_month_name}_{selected_year}.csv",
        "text/csv",
        type="primary",
    )

with col_dl2:
    fee_rows = []
    for emp, entries in st.session_state["extra_fees"].items():
        for e in entries:
            fee_rows.append({
                "employee": emp,
                "month": selected_month_name,
                "year": selected_year,
                "type": e["type"],
                "amount": e["amount"],
                "notes": e["notes"],
            })

    fees_csv_bytes = pd.DataFrame(fee_rows).to_csv(index=False).encode("utf-8")

    st.download_button(
        "⬇️ Download Fee/Credit (.csv)",
        fees_csv_bytes,
        f"fees_credits_{selected_month_name}_{selected_year}.csv",
        "text/csv",
        type="primary",
    )

# ── Step 8: AI Report ─────────────────────────────────────────────────────────
st.header("Step 8: AI Report")
st.caption(
    "⚠️ Employee names and session data will be sent to an external cloud AI. "
    "Skip this section if you have privacy concerns."
)

if st.button("Generate AI Report"):
    with st.spinner("Asking Lorelei..."):
        summary = get_ai_summary(df, selected_month_name, selected_year)

    st.session_state["ai_summary"] = summary

if "ai_summary" in st.session_state:
    st.subheader("AI Monthly Analytics Summary")
    st.write(st.session_state["ai_summary"])

    report_filename, report_text = prepare_report_download(
        st.session_state["ai_summary"],
        selected_month_name,
        selected_year,
    )

    st.download_button(
        label="Download Report (.txt)",
        data=report_text,
        file_name=report_filename,
        mime="text/plain",
        type="primary",
    )