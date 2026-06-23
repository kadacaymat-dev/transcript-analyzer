import time
import pandas as pd
import streamlit as st

from config.settings import AGREEMENT_THRESHOLD, ANALYSIS_MODES
from pipeline.classify import build_rubric_context, classify_row, check_values
from pipeline.sampling import required_sample_size, sample_rows

st.set_page_config(page_title="Text Analyzer", layout="wide")
st.title("📊 Text Analyzer")

# ── Session state defaults ──────────────────────────────────────
for key, default in {
    "transcripts": None,
    "rubric": None,
    "qa_sample": None,
    "qa_reviews": {},
    "t_col_map": None,
    "r_col_map": None,
    "analysis_mode": "Transcript Analysis",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Analysis mode selector ──────────────────────────────────────
st.sidebar.markdown("### Analysis Type")
mode_key = st.sidebar.selectbox(
    "What are you analyzing?",
    list(ANALYSIS_MODES.keys()),
    index=list(ANALYSIS_MODES.keys()).index(st.session_state.analysis_mode),
    label_visibility="collapsed",
)
if mode_key != st.session_state.analysis_mode:
    # Reset data when mode changes
    st.session_state.analysis_mode = mode_key
    st.session_state.transcripts = None
    st.session_state.rubric = None
    st.session_state.qa_sample = None
    st.session_state.qa_reviews = {}
    st.rerun()

mode = ANALYSIS_MODES[mode_key]
st.sidebar.caption(mode["description"])


def _autodetect(columns: list[str], candidates: list[str]) -> str:
    """Return the first column name that fuzzy-matches any candidate keyword."""
    for col in columns:
        for c in candidates:
            if c.lower() in col.lower():
                return col
    return columns[0]


def map_columns(df: pd.DataFrame, field_hints: dict, key_prefix: str) -> dict:
    """
    Render a row of selectboxes — one per required field — and return
    a {internal_name: selected_column} mapping.
    field_hints: {internal_name: [keyword hints for autodetect]}
    """
    cols = df.columns.tolist()
    mapping = {}
    ui_cols = st.columns(len(field_hints))
    for i, (field, hints) in enumerate(field_hints.items()):
        default = _autodetect(cols, hints)
        idx = cols.index(default)
        mapping[field] = ui_cols[i].selectbox(
            f"Which column is **{field}**?",
            options=cols,
            index=idx,
            key=f"{key_prefix}_{field}",
        )
    return mapping

# ── Sidebar navigation ──────────────────────────────────────────
step = st.sidebar.radio(
    "Steps",
    [
        "1 · Upload Data",
        "2 · Classify",
        "3 · Validate",
        "4 · QA Review",
        "5 · Report",
    ],
)

# ═══════════════════════════════════════════════════════════════
# STEP 1 — Upload Data
# ═══════════════════════════════════════════════════════════════
if step == "1 · Upload Data":
    st.header("Step 1 · Upload Data")

    # ── Transcripts ──
    st.subheader("Transcripts")
    t_file = st.file_uploader("Upload your transcripts CSV", type="csv", key="t_upload")
    if t_file:
        raw_df = pd.read_csv(t_file, encoding="utf-8-sig")
        raw_df.columns = raw_df.columns.str.strip()
        st.success(f"Detected {len(raw_df)} rows and {len(raw_df.columns)} columns.")

        st.markdown("**Map your columns** — select which column in your file corresponds to each field:")
        t_map = map_columns(raw_df, mode["text_fields"], key_prefix="t")

        if st.button("✅ Confirm Transcript Mapping", type="primary"):
            df = raw_df.rename(columns={v: k for k, v in t_map.items()})
            for col in CLASSIFICATION_COLUMNS:
                if col not in df.columns:
                    df[col] = ""
            st.session_state.transcripts = df
            st.session_state.t_col_map = t_map
            st.rerun()

    if st.session_state.transcripts is not None:
        st.success(f"✅ Transcripts ready — {len(st.session_state.transcripts)} rows loaded.")
        with st.expander("Preview"):
            st.dataframe(st.session_state.transcripts.head(), use_container_width=True)

    st.divider()

    # ── Rubric ──
    st.subheader("Rubric")
    r_file = st.file_uploader("Upload your rubric CSV", type="csv", key="r_upload")
    if r_file:
        raw_rdf = pd.read_csv(r_file, encoding="utf-8-sig")
        raw_rdf.columns = raw_rdf.columns.str.strip()
        st.success(f"Detected {len(raw_rdf)} rows and {len(raw_rdf.columns)} columns.")

        st.markdown("**Map your columns:**")
        r_map = map_columns(
            raw_rdf,
            {
                "Dimension Name":                   ["dimension", "name", "category", "label"],
                "Possible Values (comma-separated)": ["values", "possible", "options", "allowed"],
                "What This Measures":               ["measures", "description", "what", "definition"],
                "Active?":                          ["active", "enabled", "include", "use"],
            },
            key_prefix="r",
        )

        if st.button("✅ Confirm Rubric Mapping", type="primary"):
            rdf = raw_rdf.rename(columns={v: k for k, v in r_map.items()})
            st.session_state.rubric = rdf
            st.session_state.r_col_map = r_map
            st.rerun()

    if st.session_state.rubric is not None:
        st.success(f"✅ Rubric ready — {len(st.session_state.rubric)} dimensions loaded.")
        with st.expander("Preview"):
            st.dataframe(st.session_state.rubric, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# STEP 2 — Classify
# ═══════════════════════════════════════════════════════════════
elif step == "2 · Classify":
    st.header("Step 2 · Analyze")

    if st.session_state.transcripts is None or st.session_state.rubric is None:
        st.warning("Upload data and rubric in Step 1 first.")
        st.stop()

    df = st.session_state.transcripts
    rubric_context, allowed = build_rubric_context(st.session_state.rubric)

    # First rubric dimension drives the "classified" check
    first_dim = list(allowed.keys())[0] if allowed else None
    first_field = first_dim.lower().replace(" ", "_") if first_dim else "theme"
    classified_col = first_field.replace("_", " ").title()

    if classified_col not in df.columns:
        df[classified_col] = ""
    if "Confidence" not in df.columns:
        df["Confidence"] = ""
    if "AI Notes" not in df.columns:
        df["AI Notes"] = ""
    if "Value Check" not in df.columns:
        df["Value Check"] = ""

    unclassified = df[df[classified_col].isna() | (df[classified_col] == "")]
    st.info(f"{len(unclassified)} unanalyzed rows · {len(df) - len(unclassified)} already done")

    if st.button("▶ Run Analysis", type="primary"):
        progress = st.progress(0)
        status = st.empty()
        errors = 0
        prompt_context = mode["prompt_context"]

        indices = unclassified.index.tolist()
        for i, idx in enumerate(indices):
            row = df.loc[idx]
            status.text(f"Analyzing row {i + 1} of {len(indices)}…")
            try:
                result = classify_row(
                    rubric_context,
                    str(row.get("Text", "")),
                    str(row.get("Summary", "")),
                    prompt_context=prompt_context,
                )
                # Write all rubric dimension results back dynamically
                for dim in allowed:
                    field = dim.lower().replace(" ", "_")
                    col = field.replace("_", " ").title()
                    if col not in df.columns:
                        df[col] = ""
                    df.at[idx, col] = result.get(field, "")
                df.at[idx, "Confidence"] = result.get("confidence", "")
                df.at[idx, "AI Notes"] = result.get("ai_notes", "")
                df.at[idx, "Value Check"] = check_values(result, allowed)
            except Exception as e:
                errors += 1
                df.at[idx, "AI Notes"] = f"ERROR: {e}"
            progress.progress((i + 1) / len(indices))
            time.sleep(0.3)

        st.session_state.transcripts = df
        status.text("")
        st.success(f"Done! {len(indices) - errors} classified · {errors} errors")

    st.dataframe(
        st.session_state.transcripts[["Date", "User Request Summary", "Intent", "Failure Mode", "Escalation Trigger", "Confidence", "Value Check"]],
        use_container_width=True,
    )

# ═══════════════════════════════════════════════════════════════
# STEP 3 — Validate
# ═══════════════════════════════════════════════════════════════
elif step == "3 · Validate":
    st.header("Step 3 · Validate Classifications")

    if st.session_state.transcripts is None or st.session_state.rubric is None:
        st.warning("Complete Steps 1 and 2 first.")
        st.stop()

    df = st.session_state.transcripts
    _, allowed = build_rubric_context(st.session_state.rubric)

    classified = df[df["Intent"].notna() & (df["Intent"] != "")]
    ok = (classified["Value Check"] == "OK").sum()
    invalid = (classified["Value Check"].str.startswith("INVALID", na=False)).sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Classified", len(classified))
    col2.metric("✅ Valid", ok)
    col3.metric("⚠️ Invalid", invalid)

    if invalid > 0:
        st.subheader("Invalid rows")
        st.dataframe(
            classified[classified["Value Check"].str.startswith("INVALID", na=False)][
                ["Date", "User Request Summary", "Failure Mode", "Escalation Trigger", "Confidence", "Value Check"]
            ],
            use_container_width=True,
        )
        st.info("Re-run Step 2 to reclassify these rows, or fix them manually in QA Review.")
    else:
        st.success("All classifications match the rubric.")

# ═══════════════════════════════════════════════════════════════
# STEP 4 — QA Review
# ═══════════════════════════════════════════════════════════════
elif step == "4 · QA Review":
    st.header("Step 4 · QA Review")

    if st.session_state.transcripts is None:
        st.warning("Complete Steps 1–3 first.")
        st.stop()

    df = st.session_state.transcripts

    # Sampling config
    with st.expander("⚙️ Sampling Configuration", expanded=st.session_state.qa_sample is None):
        confidence = st.selectbox("Confidence Level", ["90%", "95%", "99%"], index=1)
        margin = st.selectbox("Margin of Error", ["±3%", "±5%", "±10%"], index=1)
        method = st.selectbox("Sampling Method", ["Stratified", "Random", "Low-confidence priority"])
        classified_n = len(df[df["Intent"].notna() & (df["Intent"] != "")])
        n = required_sample_size(classified_n, confidence, margin)
        st.info(f"Required sample: **{n} rows** ({n/classified_n*100:.1f}% of {classified_n} classified)")

        if st.button("Build QA Sample"):
            sample = sample_rows(df, method, n).copy()
            sample["QA Status"] = "pending"
            sample["Reviewer Notes"] = ""
            sample["Override Intent"] = ""
            sample["Override Failure Mode"] = ""
            sample["Override Escalation Trigger"] = ""
            st.session_state.qa_sample = sample
            st.session_state.qa_reviews = {}
            st.rerun()

    if st.session_state.qa_sample is None:
        st.stop()

    sample = st.session_state.qa_sample
    reviews = st.session_state.qa_reviews

    # Agreement score
    approved = sum(1 for v in reviews.values() if v["status"] == "approved")
    overridden = sum(1 for v in reviews.values() if v["status"] == "override")
    reviewed = approved + overridden
    agreement = (approved / reviewed * 100) if reviewed > 0 else None

    col1, col2, col3 = st.columns(3)
    col1.metric("Sampled", len(sample))
    col2.metric("Reviewed", reviewed)
    if agreement is not None:
        color = "normal" if agreement >= AGREEMENT_THRESHOLD else "inverse"
        col3.metric("Agreement", f"{agreement:.1f}%", delta=f"threshold {AGREEMENT_THRESHOLD}%", delta_color=color)
    else:
        col3.metric("Agreement", "—")

    if agreement is not None and agreement < AGREEMENT_THRESHOLD:
        st.warning(f"⚠️ Agreement is below {AGREEMENT_THRESHOLD}%. Review more rows or refine the rubric.")
    elif agreement is not None:
        st.success(f"✅ Agreement passes the {AGREEMENT_THRESHOLD}% threshold.")

    st.divider()

    # Review each row
    for i, (_, row) in enumerate(sample.iterrows()):
        saved = reviews.get(i, {})
        with st.expander(f"Row {i+1} · {row.get('User Request Summary', '')[:80]}", expanded=saved.get("status") == "pending"):
            st.markdown(f"**AI Intent:** {row['Intent']}  \n**Failure Mode:** {row['Failure Mode']}  \n**Escalation Trigger:** {row['Escalation Trigger']}  \n**Confidence:** {row['Confidence']}")
            st.caption(f"AI Notes: {row.get('AI Notes', '')}")

            status = st.selectbox(
                "QA Status",
                ["pending", "approved", "override", "skip"],
                index=["pending", "approved", "override", "skip"].index(saved.get("status", "pending")),
                key=f"status_{i}",
            )
            notes = st.text_input("Reviewer Notes", value=saved.get("notes", ""), key=f"notes_{i}")

            o_intent, o_fm, o_et = "", "", ""
            if status == "override":
                o_intent = st.text_input("Override Intent", value=saved.get("o_intent", ""), key=f"oi_{i}")
                o_fm = st.text_input("Override Failure Mode", value=saved.get("o_fm", ""), key=f"ofm_{i}")
                o_et = st.text_input("Override Escalation Trigger", value=saved.get("o_et", ""), key=f"oet_{i}")

            if st.button("Save", key=f"save_{i}"):
                reviews[i] = {"status": status, "notes": notes, "o_intent": o_intent, "o_fm": o_fm, "o_et": o_et}
                st.session_state.qa_reviews = reviews
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# STEP 5 — Report
# ═══════════════════════════════════════════════════════════════
elif step == "5 · Report":
    st.header("Step 5 · Generate Report")

    if st.session_state.transcripts is None:
        st.warning("Complete Steps 1–4 first.")
        st.stop()

    df = st.session_state.transcripts.copy()
    reviews = st.session_state.qa_reviews or {}

    # Apply overrides
    sample = st.session_state.qa_sample
    if sample is not None:
        for i, (orig_idx, _) in enumerate(sample.iterrows()):
            r = reviews.get(i, {})
            if r.get("status") == "override":
                if r.get("o_intent"): df.at[orig_idx, "Intent"] = r["o_intent"]
                if r.get("o_fm"): df.at[orig_idx, "Failure Mode"] = r["o_fm"]
                if r.get("o_et"): df.at[orig_idx, "Escalation Trigger"] = r["o_et"]

    classified = df[df["Intent"].notna() & (df["Intent"] != "")]
    total = len(classified)

    if total == 0:
        st.warning("No classified rows to report on.")
        st.stop()

    # Metrics
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Conversations", total)
    conf_counts = classified["Confidence"].str.lower().value_counts()
    col2.metric("High Confidence", conf_counts.get("high", 0))
    col3.metric("Low Confidence", conf_counts.get("low", 0))

    st.divider()

    # Failure Mode breakdown
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Failure Mode Breakdown")
        fm = classified["Failure Mode"].value_counts().reset_index()
        fm.columns = ["Failure Mode", "Count"]
        fm["% of Total"] = (fm["Count"] / total * 100).round(1).astype(str) + "%"
        st.dataframe(fm, use_container_width=True, hide_index=True)

    with col_b:
        st.subheader("Escalation Trigger Breakdown")
        et = classified["Escalation Trigger"].value_counts().reset_index()
        et.columns = ["Escalation Trigger", "Count"]
        et["% of Total"] = (et["Count"] / total * 100).round(1).astype(str) + "%"
        st.dataframe(et, use_container_width=True, hide_index=True)

    st.divider()

    # QA summary
    st.subheader("QA Summary")
    approved = sum(1 for v in reviews.values() if v["status"] == "approved")
    overridden = sum(1 for v in reviews.values() if v["status"] == "override")
    reviewed = approved + overridden
    agreement = f"{approved / reviewed * 100:.1f}%" if reviewed > 0 else "N/A"
    st.markdown(f"- Rows reviewed: **{reviewed}** · Approved: **{approved}** · Overridden: **{overridden}**")
    st.markdown(f"- AI–Human Agreement: **{agreement}**")

    st.divider()

    # Download
    st.subheader("Export")
    csv = classified.to_csv(index=False)
    st.download_button("⬇️ Download classified data (CSV)", csv, "classified_transcripts.csv", "text/csv")
