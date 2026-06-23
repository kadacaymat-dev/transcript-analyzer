import time
import pandas as pd
import streamlit as st

from config.settings import REQUIRED_COLUMNS, CLASSIFICATION_COLUMNS, AGREEMENT_THRESHOLD
from pipeline.classify import build_rubric_context, classify_row, check_values
from pipeline.sampling import required_sample_size, sample_rows

st.set_page_config(page_title="Transcript Analyzer", layout="wide")
st.title("📊 Transcript Analyzer")

# ── Session state defaults ──────────────────────────────────────
for key, default in {
    "transcripts": None,
    "rubric": None,
    "qa_sample": None,
    "qa_reviews": {},
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Transcripts CSV")
        t_file = st.file_uploader("Upload transcripts", type="csv", key="t_upload")
        if t_file:
            df = pd.read_csv(t_file, encoding="utf-8-sig")
            df.columns = df.columns.str.strip()
            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                st.error(f"Missing required columns: {', '.join(missing)}")
                st.caption(f"Columns found: {', '.join(df.columns.tolist())}")
            else:
                for col in CLASSIFICATION_COLUMNS:
                    if col not in df.columns:
                        df[col] = ""
                st.session_state.transcripts = df
                st.success(f"Loaded {len(df)} rows.")
                st.dataframe(df.head(), use_container_width=True)

    with col2:
        st.subheader("Rubric CSV")
        r_file = st.file_uploader("Upload rubric", type="csv", key="r_upload")
        if r_file:
            rdf = pd.read_csv(r_file, encoding="utf-8-sig")
            rdf.columns = rdf.columns.str.strip()
            st.session_state.rubric = rdf
            st.success(f"Loaded {len(rdf)} rubric dimensions.")
            st.dataframe(rdf, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# STEP 2 — Classify
# ═══════════════════════════════════════════════════════════════
elif step == "2 · Classify":
    st.header("Step 2 · Classify Transcripts")

    if st.session_state.transcripts is None or st.session_state.rubric is None:
        st.warning("Upload transcripts and rubric in Step 1 first.")
        st.stop()

    df = st.session_state.transcripts
    unclassified = df[df["Intent"].isna() | (df["Intent"] == "")]
    st.info(f"{len(unclassified)} unclassified rows · {len(df) - len(unclassified)} already done")

    if st.button("▶ Run Classification", type="primary"):
        rubric_context, allowed = build_rubric_context(st.session_state.rubric)
        progress = st.progress(0)
        status = st.empty()
        errors = 0

        indices = unclassified.index.tolist()
        for i, idx in enumerate(indices):
            row = df.loc[idx]
            status.text(f"Classifying row {i + 1} of {len(indices)}…")
            try:
                result = classify_row(
                    rubric_context,
                    str(row.get("Transcript", "")),
                    str(row.get("User Request Summary", "")),
                )
                df.at[idx, "Intent"] = result.get("intent", "")
                df.at[idx, "Failure Mode"] = result.get("failure_mode", "")
                df.at[idx, "Escalation Trigger"] = result.get("escalation_trigger", "")
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
