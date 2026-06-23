import time
import pandas as pd
import streamlit as st

from config.settings import AGREEMENT_THRESHOLD, ANALYSIS_MODES
from pipeline.classify import build_rubric_context, classify_row, check_values
from pipeline.golden_set import (
    new_golden_set, load_golden_set, export_golden_set,
    record_run, add_examples, classify_with_examples,
)
from pipeline.sampling import required_sample_size, sample_rows

st.set_page_config(page_title="Text Analyzer", layout="wide")
st.title("📊 Text Analyzer")

# ── Session state ───────────────────────────────────────────────
for key, default in {
    "study_type": None,       # "Ad-hoc" | "Recurring"
    "series_name": "",
    "analysis_mode": "Transcript Analysis",
    "golden_set": None,
    "transcripts": None,
    "rubric": None,
    "qa_sample": None,
    "qa_reviews": {},
    "t_col_map": None,
    "r_col_map": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Helpers ─────────────────────────────────────────────────────
def _autodetect(columns, candidates):
    for col in columns:
        for c in candidates:
            if c.lower() in col.lower():
                return col
    return columns[0]


def map_columns(df, field_hints, key_prefix):
    cols = df.columns.tolist()
    mapping = {}
    ui_cols = st.columns(len(field_hints))
    for i, (field, hints) in enumerate(field_hints.items()):
        default = _autodetect(cols, hints)
        mapping[field] = ui_cols[i].selectbox(
            f"**{field}**",
            options=cols,
            index=cols.index(default),
            key=f"{key_prefix}_{field}",
        )
    return mapping


def get_classified_col(df, allowed):
    if not allowed:
        return None
    first_field = list(allowed.keys())[0].lower().replace(" ", "_")
    col = first_field.replace("_", " ").title()
    return col if col in df.columns else None


# ── Sidebar ─────────────────────────────────────────────────────
is_setup_done = st.session_state.study_type is not None

if is_setup_done:
    st.sidebar.markdown(
        f"**{st.session_state.study_type}**  \n"
        f"{st.session_state.analysis_mode}"
        + (f"  \n*{st.session_state.series_name}*" if st.session_state.series_name else "")
    )
    if st.sidebar.button("↩ Change Study Setup"):
        for k in ["study_type", "series_name", "golden_set", "transcripts", "rubric", "qa_sample", "qa_reviews"]:
            st.session_state[k] = None if k != "qa_reviews" and k != "series_name" else ({} if k == "qa_reviews" else "")
        st.rerun()
    st.sidebar.divider()

# Build step list based on study type
if not is_setup_done:
    steps = ["0 · Study Setup"]
elif st.session_state.study_type == "Recurring":
    steps = ["1 · Upload Data", "2 · Analyze", "3 · Validate", "4 · QA Review", "5 · Golden Set", "6 · Report"]
else:
    steps = ["1 · Upload Data", "2 · Analyze", "3 · Validate", "4 · QA Review", "5 · Report"]

step = st.sidebar.radio("Steps", steps)

# ── Golden set badge in sidebar ─────────────────────────────────
if st.session_state.golden_set:
    gs = st.session_state.golden_set
    n_examples = len(gs.get("examples", []))
    n_runs = len(gs.get("runs", []))
    st.sidebar.markdown(f"**Golden Set:** {n_examples} examples · {n_runs} past runs")

# ═══════════════════════════════════════════════════════════════
# STEP 0 — Study Setup
# ═══════════════════════════════════════════════════════════════
if step == "0 · Study Setup":
    st.header("Step 0 · Study Setup")
    st.markdown("Choose how you want to run this analysis.")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
### ⚡ Ad-hoc
Fast and disposable. Good for one-off studies where you don't need to build on past results.

- No golden dataset involved
- QA review is a quality gate for this study only
- Export CSV/JSON if you want to archive results
        """)
        if st.button("Start Ad-hoc Study", use_container_width=True):
            st.session_state.study_type = "Ad-hoc"
            st.rerun()

    with col2:
        st.markdown("""
### 🔁 Recurring
Builds institutional knowledge over time. Good for studies you run monthly or on the same rubric repeatedly (e.g. CSAT, AHT).

- Past verified examples are injected into the AI prompt → improves accuracy each run
- After QA review, promote good rows to a persistent golden set
- Agreement rate tracked across runs
        """)
        series = st.text_input("Series name (e.g. 'Commercial Ops Escalations')", key="series_input")
        gs_file = st.file_uploader("Upload existing golden set JSON (optional — skip for first run)", type="json")
        if st.button("Start Recurring Study", use_container_width=True, disabled=not series.strip()):
            st.session_state.study_type = "Recurring"
            st.session_state.series_name = series.strip()
            if gs_file:
                st.session_state.golden_set = load_golden_set(gs_file.read())
                n = len(st.session_state.golden_set.get("examples", []))
                st.success(f"Loaded golden set with {n} examples.")
            else:
                st.session_state.golden_set = new_golden_set(series.strip(), st.session_state.analysis_mode)
            st.rerun()

# ═══════════════════════════════════════════════════════════════
# STEP 1 — Upload Data
# ═══════════════════════════════════════════════════════════════
elif step == "1 · Upload Data":
    st.header("Step 1 · Upload Data")
    mode = ANALYSIS_MODES[st.session_state.analysis_mode]

    # Analysis mode selector (only if not locked to a golden set's mode)
    gs = st.session_state.golden_set
    if gs and gs.get("mode"):
        st.info(f"Analysis mode locked to **{gs['mode']}** (set by golden set series).")
        st.session_state.analysis_mode = gs["mode"]
        mode = ANALYSIS_MODES[gs["mode"]]
    else:
        new_mode = st.selectbox(
            "Analysis type",
            list(ANALYSIS_MODES.keys()),
            index=list(ANALYSIS_MODES.keys()).index(st.session_state.analysis_mode),
        )
        if new_mode != st.session_state.analysis_mode:
            st.session_state.analysis_mode = new_mode
            st.rerun()
        mode = ANALYSIS_MODES[new_mode]

    st.caption(mode["description"])
    st.divider()

    # Transcripts upload
    st.subheader("Data")
    t_file = st.file_uploader("Upload your CSV", type="csv", key="t_upload")
    if t_file:
        raw_df = pd.read_csv(t_file, encoding="utf-8-sig")
        raw_df.columns = raw_df.columns.str.strip()
        st.success(f"Detected {len(raw_df)} rows · {len(raw_df.columns)} columns.")

        st.markdown("**Map your columns:**")
        t_map = map_columns(raw_df, mode["text_fields"], key_prefix="t")

        if st.button("✅ Confirm Mapping", type="primary"):
            df = raw_df.rename(columns={v: k for k, v in t_map.items()})
            for col in ["Confidence", "AI Notes", "Value Check"]:
                if col not in df.columns:
                    df[col] = ""
            st.session_state.transcripts = df
            st.session_state.t_col_map = t_map
            st.rerun()

    if st.session_state.transcripts is not None:
        st.success(f"✅ {len(st.session_state.transcripts)} rows loaded.")
        with st.expander("Preview"):
            st.dataframe(st.session_state.transcripts.head(), use_container_width=True)

    st.divider()

    # Rubric upload
    st.subheader("Rubric")
    r_file = st.file_uploader("Upload your rubric CSV", type="csv", key="r_upload")
    if r_file:
        raw_rdf = pd.read_csv(r_file, encoding="utf-8-sig")
        raw_rdf.columns = raw_rdf.columns.str.strip()
        st.success(f"Detected {len(raw_rdf)} dimensions.")

        st.markdown("**Map your columns:**")
        r_map = map_columns(
            raw_rdf,
            {
                "Dimension Name": ["dimension", "name", "category", "label"],
                "Possible Values (comma-separated)": ["values", "possible", "options", "allowed"],
                "What This Measures": ["measures", "description", "what", "definition"],
                "Active?": ["active", "enabled", "include", "use"],
            },
            key_prefix="r",
        )

        if st.button("✅ Confirm Rubric", type="primary"):
            rdf = raw_rdf.rename(columns={v: k for k, v in r_map.items()})
            st.session_state.rubric = rdf
            st.session_state.r_col_map = r_map
            st.rerun()

    if st.session_state.rubric is not None:
        st.success(f"✅ {len(st.session_state.rubric)} rubric dimensions loaded.")
        with st.expander("Preview"):
            st.dataframe(st.session_state.rubric, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# STEP 2 — Analyze
# ═══════════════════════════════════════════════════════════════
elif step == "2 · Analyze":
    st.header("Step 2 · Analyze")

    if st.session_state.transcripts is None or st.session_state.rubric is None:
        st.warning("Upload data and rubric in Step 1 first.")
        st.stop()

    df = st.session_state.transcripts
    mode = ANALYSIS_MODES[st.session_state.analysis_mode]
    rubric_context, allowed = build_rubric_context(st.session_state.rubric)

    # Ensure output columns exist
    for dim in allowed:
        col = dim.lower().replace(" ", "_").replace("_", " ").title()
        if col not in df.columns:
            df[col] = ""
    for col in ["Confidence", "AI Notes", "Value Check"]:
        if col not in df.columns:
            df[col] = ""

    classified_col = get_classified_col(df, allowed)
    unclassified = df[df[classified_col].isna() | (df[classified_col] == "")] if classified_col else df

    # Golden set info for recurring studies
    gs = st.session_state.golden_set
    examples = gs.get("examples", []) if gs else []
    if st.session_state.study_type == "Recurring":
        if examples:
            st.success(f"🎯 **{len(examples)} golden examples** will be injected into the prompt as few-shot context.")
        else:
            st.info("No golden examples yet — this first run will build them after QA review.")

    st.info(f"{len(unclassified)} unanalyzed rows · {len(df) - len(unclassified)} already done")

    if st.button("▶ Run Analysis", type="primary"):
        progress = st.progress(0)
        status = st.empty()
        errors = 0
        prompt_context = mode["prompt_context"]
        use_examples = st.session_state.study_type == "Recurring" and len(examples) > 0

        indices = unclassified.index.tolist()
        for i, idx in enumerate(indices):
            row = df.loc[idx]
            status.text(f"Analyzing row {i + 1} of {len(indices)}…")
            try:
                if use_examples:
                    result = classify_with_examples(
                        rubric_context, examples,
                        str(row.get("Text", "")), str(row.get("Summary", "")),
                        prompt_context,
                    )
                else:
                    result = classify_row(
                        rubric_context,
                        str(row.get("Text", "")), str(row.get("Summary", "")),
                        prompt_context=prompt_context,
                    )
                for dim in allowed:
                    field = dim.lower().replace(" ", "_")
                    col = field.replace("_", " ").title()
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
        st.success(f"Done! {len(indices) - errors} analyzed · {errors} errors")

    display_cols = ["Date", "Summary"] + [
        dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed
    ] + ["Confidence", "Value Check"]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[display_cols], use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# STEP 3 — Validate
# ═══════════════════════════════════════════════════════════════
elif step == "3 · Validate":
    st.header("Step 3 · Validate")

    if st.session_state.transcripts is None or st.session_state.rubric is None:
        st.warning("Complete Steps 1 and 2 first.")
        st.stop()

    df = st.session_state.transcripts
    _, allowed = build_rubric_context(st.session_state.rubric)
    classified_col = get_classified_col(df, allowed)
    classified = df[df[classified_col].notna() & (df[classified_col] != "")] if classified_col else df

    ok = (classified["Value Check"] == "OK").sum()
    invalid = classified["Value Check"].str.startswith("INVALID", na=False).sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("Classified", len(classified))
    col2.metric("✅ Valid", ok)
    col3.metric("⚠️ Invalid", invalid)

    if invalid > 0:
        st.subheader("Invalid rows")
        inv_cols = [c for c in [classified_col, "Confidence", "Value Check"] if c in classified.columns]
        st.dataframe(
            classified[classified["Value Check"].str.startswith("INVALID", na=False)][inv_cols],
            use_container_width=True,
        )
    else:
        st.success("All classifications match the rubric. ✅")

# ═══════════════════════════════════════════════════════════════
# STEP 4 — QA Review
# ═══════════════════════════════════════════════════════════════
elif step == "4 · QA Review":
    st.header("Step 4 · QA Review")

    if st.session_state.transcripts is None:
        st.warning("Complete Steps 1–3 first.")
        st.stop()

    df = st.session_state.transcripts
    _, allowed = build_rubric_context(st.session_state.rubric)

    with st.expander("⚙️ Sampling Configuration", expanded=st.session_state.qa_sample is None):
        confidence = st.selectbox("Confidence Level", ["90%", "95%", "99%"], index=1)
        margin = st.selectbox("Margin of Error", ["±3%", "±5%", "±10%"], index=1)
        method = st.selectbox("Sampling Method", ["Stratified", "Random", "Low-confidence priority"])
        classified_col = get_classified_col(df, allowed)
        classified_n = len(df[df[classified_col].notna() & (df[classified_col] != "")]) if classified_col else 0
        n = required_sample_size(classified_n, confidence, margin)
        st.info(f"Required sample: **{n} rows** ({n/classified_n*100:.1f}% of {classified_n} classified)" if classified_n else "No classified rows yet.")

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

    approved = sum(1 for v in reviews.values() if v["status"] == "approved")
    overridden = sum(1 for v in reviews.values() if v["status"] == "override")
    reviewed = approved + overridden
    agreement = (approved / reviewed * 100) if reviewed > 0 else None

    col1, col2, col3 = st.columns(3)
    col1.metric("Sampled", len(sample))
    col2.metric("Reviewed", reviewed)
    if agreement is not None:
        delta_color = "normal" if agreement >= AGREEMENT_THRESHOLD else "inverse"
        col3.metric("Agreement", f"{agreement:.1f}%", delta=f"threshold {AGREEMENT_THRESHOLD}%", delta_color=delta_color)
    else:
        col3.metric("Agreement", "—")

    if agreement is not None and agreement < AGREEMENT_THRESHOLD:
        st.warning(f"⚠️ Agreement is below {AGREEMENT_THRESHOLD}%. Review more rows or refine the rubric.")
    elif agreement is not None:
        st.success(f"✅ Passes the {AGREEMENT_THRESHOLD}% threshold.")

    st.divider()

    dim_cols = [dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed]

    for i, (_, row) in enumerate(sample.iterrows()):
        saved = reviews.get(i, {})
        with st.expander(f"Row {i+1} · {str(row.get('Summary', ''))[:80]}", expanded=saved.get("status") == "pending"):
            for col in dim_cols:
                if col in row:
                    st.markdown(f"**{col}:** {row[col]}")
            st.markdown(f"**Confidence:** {row.get('Confidence', '')}  \n**AI Notes:** {row.get('AI Notes', '')}")

            status = st.selectbox(
                "QA Status", ["pending", "approved", "override", "skip"],
                index=["pending", "approved", "override", "skip"].index(saved.get("status", "pending")),
                key=f"status_{i}",
            )
            notes = st.text_input("Reviewer Notes", value=saved.get("notes", ""), key=f"notes_{i}")

            overrides = {}
            if status == "override":
                for col in dim_cols:
                    overrides[col] = st.text_input(f"Override {col}", value=saved.get(f"o_{col}", ""), key=f"o_{col}_{i}")

            if st.button("Save", key=f"save_{i}"):
                reviews[i] = {"status": status, "notes": notes, **{f"o_{col}": v for col, v in overrides.items()}}
                st.session_state.qa_reviews = reviews
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# STEP 5 — Golden Set  (Recurring only)
# ═══════════════════════════════════════════════════════════════
elif step == "5 · Golden Set":
    st.header("Step 5 · Save to Golden Set")

    reviews = st.session_state.qa_reviews or {}
    sample = st.session_state.qa_sample
    df = st.session_state.transcripts
    gs = st.session_state.golden_set
    _, allowed = build_rubric_context(st.session_state.rubric)
    dim_cols = [dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed]

    if not reviews or sample is None:
        st.warning("Complete QA Review (Step 4) first.")
        st.stop()

    approved = sum(1 for v in reviews.values() if v["status"] == "approved")
    overridden = sum(1 for v in reviews.values() if v["status"] == "override")
    reviewed = approved + overridden
    agreement = (approved / reviewed * 100) if reviewed > 0 else None

    st.markdown(f"**Series:** {gs['series']}  \n**Existing examples:** {len(gs['examples'])}  \n**Past runs:** {len(gs['runs'])}")

    if agreement is not None:
        st.metric("Agreement this run", f"{agreement:.1f}%")
    st.divider()

    # Preview what will be promoted
    promotable = []
    for i, (orig_idx, row) in enumerate(sample.iterrows()):
        r = reviews.get(i, {})
        if r.get("status") not in ("approved", "override"):
            continue
        clf = {}
        for col in dim_cols:
            field = col.lower().replace(" ", "_")
            clf[field] = r.get(f"o_{col}") or str(row.get(col, ""))
        clf["confidence"] = str(row.get("Confidence", ""))
        promotable.append({
            "text": str(row.get("Text", "")),
            "summary": str(row.get("Summary", "")),
            "classifications": clf,
        })

    st.subheader(f"{len(promotable)} rows ready to promote")
    if promotable:
        preview_df = pd.DataFrame([{
            "Summary": p["summary"][:80],
            **{k: v for k, v in p["classifications"].items()}
        } for p in promotable])
        st.dataframe(preview_df, use_container_width=True)

    if st.button("💾 Save to Golden Set", type="primary", disabled=not promotable):
        gs, added = add_examples(gs, promotable)
        gs = record_run(gs, agreement, added)
        st.session_state.golden_set = gs
        st.success(f"✅ Added {added} new examples. Golden set now has {len(gs['examples'])} total.")
        st.rerun()

    # Run history
    if gs["runs"]:
        st.divider()
        st.subheader("Agreement Rate — Run History")
        runs_df = pd.DataFrame(gs["runs"])
        runs_df = runs_df[runs_df["agreement_rate"].notna()]
        if not runs_df.empty:
            st.line_chart(runs_df.set_index("date")["agreement_rate"])
        st.dataframe(pd.DataFrame(gs["runs"]), use_container_width=True, hide_index=True)

    # Download golden set
    st.divider()
    st.download_button(
        "⬇️ Download Golden Set JSON",
        export_golden_set(gs),
        file_name=f"{gs['series'].lower().replace(' ', '-')}-golden-set.json",
        mime="application/json",
    )

# ═══════════════════════════════════════════════════════════════
# STEP 5/6 — Report
# ═══════════════════════════════════════════════════════════════
elif step in ("5 · Report", "6 · Report"):
    st.header("Report")

    if st.session_state.transcripts is None:
        st.warning("Complete the previous steps first.")
        st.stop()

    df = st.session_state.transcripts.copy()
    reviews = st.session_state.qa_reviews or {}
    sample = st.session_state.qa_sample
    _, allowed = build_rubric_context(st.session_state.rubric)
    dim_cols = [dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed]

    # Apply overrides
    if sample is not None:
        for i, (orig_idx, _) in enumerate(sample.iterrows()):
            r = reviews.get(i, {})
            if r.get("status") == "override":
                for col in dim_cols:
                    val = r.get(f"o_{col}")
                    if val:
                        df.at[orig_idx, col] = val

    classified_col = get_classified_col(df, allowed)
    classified = df[df[classified_col].notna() & (df[classified_col] != "")] if classified_col else df
    total = len(classified)

    if total == 0:
        st.warning("No classified rows to report on.")
        st.stop()

    # QA stats
    approved = sum(1 for v in reviews.values() if v["status"] == "approved")
    overridden = sum(1 for v in reviews.values() if v["status"] == "override")
    reviewed = approved + overridden
    agreement = f"{approved / reviewed * 100:.1f}%" if reviewed > 0 else "N/A"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Rows", total)
    col2.metric("Reviewed", reviewed)
    col3.metric("Agreement", agreement)
    conf_counts = classified["Confidence"].str.lower().value_counts()
    col4.metric("High Confidence", conf_counts.get("high", 0))

    st.divider()

    # One breakdown table per rubric dimension
    cols = st.columns(min(len(dim_cols), 2))
    for i, col in enumerate(dim_cols):
        if col not in classified.columns:
            continue
        with cols[i % 2]:
            st.subheader(col)
            breakdown = classified[col].value_counts().reset_index()
            breakdown.columns = [col, "Count"]
            breakdown["% of Total"] = (breakdown["Count"] / total * 100).round(1).astype(str) + "%"
            st.dataframe(breakdown, use_container_width=True, hide_index=True)

    # Golden set summary for recurring
    if st.session_state.study_type == "Recurring" and st.session_state.golden_set:
        gs = st.session_state.golden_set
        st.divider()
        st.subheader("Golden Set")
        st.markdown(f"**Series:** {gs['series']} · **{len(gs['examples'])} examples** · **{len(gs['runs'])} runs**")

    st.divider()
    st.subheader("Export")
    csv = classified.to_csv(index=False)
    st.download_button("⬇️ Download classified data (CSV)", csv, "results.csv", "text/csv")
