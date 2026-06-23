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

# ── Thumbtack design system ──────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #FFFFFF; }
[data-testid="stSidebar"] {
    background: #FAFAFA;
    border-right: 1px solid #E9ECED;
    padding-top: 1.5rem;
}

/* Typography */
h1, h2, h3 { color: #2F3033 !important; }
h1 { font-size: 1.4rem !important; font-weight: 700 !important; margin-bottom: 0.1rem !important; }
h2 { font-size: 1.15rem !important; font-weight: 600 !important; margin-top: 1.5rem !important; }
h3 { font-size: 0.95rem !important; font-weight: 600 !important; color: #676d73 !important; }
p, li { color: #2F3033; }
.stCaption p { color: #676d73 !important; font-size: 0.8rem !important; }

/* Sidebar */
[data-testid="stSidebar"] .stMarkdown p { color: #676d73; font-size: 0.8rem; }
[data-testid="stSidebar"] h4 { color: #2F3033 !important; font-size: 0.85rem !important; font-weight: 600 !important; margin-bottom: 0.5rem; }
div[role="radiogroup"] label {
    border-radius: 6px !important;
    padding: 0.4rem 0.75rem !important;
    margin-bottom: 2px !important;
    font-size: 0.875rem !important;
    color: #2F3033 !important;
}
div[role="radiogroup"] label:hover { background: #E9ECED !important; }

/* Buttons */
.stButton > button[kind="primary"] {
    background: #009FD9 !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    padding: 0.5rem 1.25rem !important;
    transition: background 0.15s;
}
.stButton > button[kind="primary"]:hover { background: #007fb0 !important; }
.stButton > button:not([kind="primary"]) {
    background: #FFFFFF !important;
    color: #009FD9 !important;
    border: 1.5px solid #009FD9 !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
}
.stButton > button:not([kind="primary"]):hover { background: #FAFAFA !important; }
.stButton > button:disabled {
    background: #E9ECED !important; color: #676d73 !important; border: none !important;
}
.stDownloadButton > button {
    background: #FFFFFF !important; color: #009FD9 !important;
    border: 1.5px solid #009FD9 !important; border-radius: 6px !important;
    font-weight: 600 !important; font-size: 0.875rem !important;
}

/* Metrics */
[data-testid="stMetric"] {
    background: #FAFAFA; border: 1px solid #E9ECED;
    border-radius: 8px; padding: 0.75rem 1rem;
}
[data-testid="stMetricLabel"] { color: #676d73 !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.04em; }
[data-testid="stMetricValue"] { color: #2F3033 !important; font-weight: 700 !important; font-size: 1.6rem !important; }

/* Alerts */
[data-testid="stAlert"] { border-radius: 6px !important; font-size: 0.875rem !important; }

/* Expanders */
[data-testid="stExpander"] {
    border: 1px solid #E9ECED !important; border-radius: 8px !important; background: #FAFAFA !important;
}
summary { font-size: 0.875rem !important; color: #2F3033 !important; }

/* Inputs */
[data-baseweb="select"] > div { border-color: #d3d4d5 !important; border-radius: 6px !important; font-size: 0.875rem !important; }
[data-baseweb="input"] > div  { border-color: #d3d4d5 !important; border-radius: 6px !important; font-size: 0.875rem !important; }
label[data-testid="stWidgetLabel"] p { font-size: 0.8rem !important; color: #676d73 !important; margin-bottom: 2px; }

/* File uploader */
[data-testid="stFileUploader"] { border: 1.5px dashed #d3d4d5 !important; border-radius: 8px !important; background: #FAFAFA !important; }

/* Progress bar */
[data-testid="stProgressBar"] > div > div { background: #009FD9 !important; }

/* Dataframes */
[data-testid="stDataFrame"] { border: 1px solid #E9ECED; border-radius: 8px; overflow: hidden; font-size: 0.85rem; }

/* Dividers */
hr { border-color: #E9ECED !important; margin: 1.25rem 0 !important; }

/* Study type cards */
.study-card {
    background: #FAFAFA; border: 1px solid #E9ECED; border-radius: 10px;
    padding: 1.5rem; height: 100%;
}
.study-card h3 { color: #2F3033 !important; font-size: 1rem !important; font-weight: 600 !important; margin-bottom: 0.5rem; }
.study-card p, .study-card li { color: #676d73 !important; font-size: 0.875rem !important; }
.study-card-active { border-color: #009FD9 !important; background: #f0fafd !important; }

/* Stat row */
.stat-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: #676d73; }
.stat-value { font-size: 1.4rem; font-weight: 700; color: #2F3033; line-height: 1.2; }

/* Page header */
.page-header { border-bottom: 2px solid #009FD9; padding-bottom: 0.6rem; margin-bottom: 1.25rem; }
.page-header h1 { margin: 0 !important; }
.page-header p { color: #676d73; font-size: 0.8rem; margin: 0.2rem 0 0; }
</style>
""", unsafe_allow_html=True)


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
            field, options=cols, index=cols.index(default),
            key=f"{key_prefix}_{field}",
        )
    return mapping


def get_classified_col(df, allowed):
    if not allowed:
        return None
    first_field = list(allowed.keys())[0].lower().replace(" ", "_")
    col = first_field.replace("_", " ").title()
    return col if col in df.columns else None


def page_header(title, subtitle=None):
    sub = f'<p>{subtitle}</p>' if subtitle else ''
    st.markdown(f'<div class="page-header"><h1>{title}</h1>{sub}</div>', unsafe_allow_html=True)


# ── Session state ───────────────────────────────────────────────
for key, default in {
    "study_type": None,
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

# ── Sidebar ─────────────────────────────────────────────────────
is_setup_done = st.session_state.study_type is not None

st.sidebar.markdown(
    '<div style="font-size:1rem;font-weight:700;color:#2F3033;margin-bottom:0.25rem">Text Analyzer</div>'
    '<div style="font-size:0.75rem;color:#676d73;margin-bottom:1rem">Thumbtack · Data & Analytics</div>',
    unsafe_allow_html=True,
)

if is_setup_done:
    study_label = st.session_state.study_type
    mode_label = st.session_state.analysis_mode
    series = st.session_state.series_name
    details = f"{mode_label}" + (f" · {series}" if series else "")
    st.sidebar.markdown(
        f'<div style="background:#E9ECED;border-radius:6px;padding:0.5rem 0.75rem;margin-bottom:0.75rem">'
        f'<div style="font-size:0.75rem;font-weight:600;color:#2F3033">{study_label}</div>'
        f'<div style="font-size:0.72rem;color:#676d73">{details}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.sidebar.button("Change setup", use_container_width=True):
        for k in ["study_type", "series_name", "golden_set", "transcripts", "rubric", "qa_sample", "qa_reviews"]:
            st.session_state[k] = None if k not in ("qa_reviews", "series_name") else ({} if k == "qa_reviews" else "")
        st.rerun()
    st.sidebar.divider()

if not is_setup_done:
    steps = ["0 · Study Setup"]
elif st.session_state.study_type == "Recurring":
    steps = ["1 · Upload Data", "2 · Analyze", "3 · Validate", "4 · QA Review", "5 · Golden Set", "6 · Report"]
else:
    steps = ["1 · Upload Data", "2 · Analyze", "3 · Validate", "4 · QA Review", "5 · Report"]

st.sidebar.markdown('<div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#676d73;margin-bottom:0.4rem">Steps</div>', unsafe_allow_html=True)
step = st.sidebar.radio("Steps", steps, label_visibility="collapsed")

if st.session_state.golden_set:
    gs = st.session_state.golden_set
    st.sidebar.divider()
    st.sidebar.markdown(
        f'<div style="font-size:0.75rem;color:#676d73">'
        f'<span style="color:#2F3033;font-weight:600">Golden Set</span><br>'
        f'{len(gs.get("examples", []))} examples · {len(gs.get("runs", []))} runs'
        f'</div>',
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════
# STEP 0 — Study Setup
# ═══════════════════════════════════════════════════════════════
if step == "0 · Study Setup":
    page_header("Study Setup", "Choose how you want to run this analysis.")

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
<div class="study-card">
<h3>Ad-hoc</h3>
<p>Fast and disposable. Good for one-off studies where you don't need to build on past results.</p>
<ul>
<li>No golden dataset</li>
<li>QA review gates this study only</li>
<li>Export results as CSV when done</li>
</ul>
</div>
""", unsafe_allow_html=True)
        st.markdown("")
        if st.button("Start ad-hoc study", use_container_width=True, type="primary"):
            st.session_state.study_type = "Ad-hoc"
            st.rerun()

    with col2:
        st.markdown("""
<div class="study-card">
<h3>Recurring</h3>
<p>Builds institutional knowledge over time. Good for monthly studies run on the same rubric — CSAT, AHT, escalation reviews.</p>
<ul>
<li>Past verified examples improve AI accuracy each run</li>
<li>Agreement rate tracked across runs</li>
<li>Golden set is portable — download and re-upload each time</li>
</ul>
</div>
""", unsafe_allow_html=True)
        st.markdown("")
        series = st.text_input("Series name", placeholder="e.g. Commercial Ops Escalations", key="series_input")
        gs_file = st.file_uploader("Golden set JSON (optional — skip for first run)", type="json")
        if st.button("Start recurring study", use_container_width=True, type="primary", disabled=not series.strip()):
            st.session_state.study_type = "Recurring"
            st.session_state.series_name = series.strip()
            if gs_file:
                st.session_state.golden_set = load_golden_set(gs_file.read())
                n = len(st.session_state.golden_set.get("examples", []))
                st.success(f"Loaded golden set — {n} existing examples.")
            else:
                st.session_state.golden_set = new_golden_set(series.strip(), st.session_state.analysis_mode)
            st.rerun()

# ═══════════════════════════════════════════════════════════════
# STEP 1 — Upload Data
# ═══════════════════════════════════════════════════════════════
elif step == "1 · Upload Data":
    page_header("Upload Data")
    mode = ANALYSIS_MODES[st.session_state.analysis_mode]

    gs = st.session_state.golden_set
    if gs and gs.get("mode"):
        st.info(f"Analysis type locked to {gs['mode']} — set by the golden set series.")
        st.session_state.analysis_mode = gs["mode"]
        mode = ANALYSIS_MODES[gs["mode"]]
    else:
        new_mode = st.selectbox("Analysis type", list(ANALYSIS_MODES.keys()),
                                index=list(ANALYSIS_MODES.keys()).index(st.session_state.analysis_mode))
        if new_mode != st.session_state.analysis_mode:
            st.session_state.analysis_mode = new_mode
            st.rerun()
        mode = ANALYSIS_MODES[new_mode]
    st.caption(mode["description"])

    st.markdown("### Data file")
    t_file = st.file_uploader("Upload a CSV file", type="csv", key="t_upload", label_visibility="collapsed")
    if t_file:
        raw_df = pd.read_csv(t_file, encoding="utf-8-sig")
        raw_df.columns = raw_df.columns.str.strip()
        st.success(f"{len(raw_df)} rows detected across {len(raw_df.columns)} columns.")

        st.markdown("**Map your columns** — select which column corresponds to each required field.")
        t_map = map_columns(raw_df, mode["text_fields"], key_prefix="t")

        if st.button("Confirm mapping", type="primary"):
            df = raw_df.rename(columns={v: k for k, v in t_map.items()})
            for col in ["Confidence", "AI Notes", "Value Check"]:
                if col not in df.columns:
                    df[col] = ""
            st.session_state.transcripts = df
            st.session_state.t_col_map = t_map
            st.rerun()

    if st.session_state.transcripts is not None:
        st.success(f"{len(st.session_state.transcripts)} rows loaded.")
        with st.expander("Preview data"):
            st.dataframe(st.session_state.transcripts.head(), use_container_width=True)

    st.divider()

    st.markdown("### Rubric file")
    r_file = st.file_uploader("Upload a rubric CSV", type="csv", key="r_upload", label_visibility="collapsed")
    if r_file:
        raw_rdf = pd.read_csv(r_file, encoding="utf-8-sig")
        raw_rdf.columns = raw_rdf.columns.str.strip()
        st.success(f"{len(raw_rdf)} dimensions detected.")

        st.markdown("**Map your columns.**")
        r_map = map_columns(raw_rdf, {
            "Dimension Name": ["dimension", "name", "category", "label"],
            "Possible Values (comma-separated)": ["values", "possible", "options", "allowed"],
            "What This Measures": ["measures", "description", "what", "definition"],
            "Active?": ["active", "enabled", "include", "use"],
        }, key_prefix="r")

        if st.button("Confirm rubric", type="primary"):
            rdf = raw_rdf.rename(columns={v: k for k, v in r_map.items()})
            st.session_state.rubric = rdf
            st.session_state.r_col_map = r_map
            st.rerun()

    if st.session_state.rubric is not None:
        st.success(f"{len(st.session_state.rubric)} rubric dimensions loaded.")
        with st.expander("Preview rubric"):
            st.dataframe(st.session_state.rubric, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# STEP 2 — Analyze
# ═══════════════════════════════════════════════════════════════
elif step == "2 · Analyze":
    page_header("Analyze")

    if st.session_state.transcripts is None or st.session_state.rubric is None:
        st.warning("Upload your data and rubric in Step 1 before continuing.")
        st.stop()

    df = st.session_state.transcripts
    mode = ANALYSIS_MODES[st.session_state.analysis_mode]
    rubric_context, allowed = build_rubric_context(st.session_state.rubric)

    for dim in allowed:
        col = dim.lower().replace(" ", "_").replace("_", " ").title()
        if col not in df.columns:
            df[col] = ""
    for col in ["Confidence", "AI Notes", "Value Check"]:
        if col not in df.columns:
            df[col] = ""

    classified_col = get_classified_col(df, allowed)
    unclassified = df[df[classified_col].isna() | (df[classified_col] == "")] if classified_col else df

    gs = st.session_state.golden_set
    examples = gs.get("examples", []) if gs else []

    c1, c2 = st.columns(2)
    c1.markdown(f'<div class="stat-label">Rows to analyze</div><div class="stat-value">{len(unclassified)}</div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="stat-label">Already done</div><div class="stat-value">{len(df) - len(unclassified)}</div>', unsafe_allow_html=True)

    if st.session_state.study_type == "Recurring":
        st.markdown("")
        if examples:
            st.info(f"{len(examples)} golden examples will be injected into the prompt to improve accuracy.")
        else:
            st.info("No golden examples yet. This first run will build them after QA review.")

    st.markdown("")
    if st.button("Run analysis", type="primary"):
        progress = st.progress(0)
        status = st.empty()
        errors = 0
        prompt_context = mode["prompt_context"]
        use_examples = st.session_state.study_type == "Recurring" and len(examples) > 0

        indices = unclassified.index.tolist()
        for i, idx in enumerate(indices):
            row = df.loc[idx]
            status.text(f"Analyzing row {i + 1} of {len(indices)}")
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
        st.success(f"Done — {len(indices) - errors} rows analyzed, {errors} errors.")

    display_cols = ["Date", "Summary"] + [
        dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed
    ] + ["Confidence", "Value Check"]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[display_cols], use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# STEP 3 — Validate
# ═══════════════════════════════════════════════════════════════
elif step == "3 · Validate":
    page_header("Validate", "Check that all AI outputs match the rubric's allowed values.")

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
    col2.metric("Valid", ok)
    col3.metric("Invalid", invalid)

    st.markdown("")
    if invalid > 0:
        st.markdown("### Rows with invalid values")
        st.caption("These rows contain values that don't match your rubric. Re-run Step 2 or correct them in QA Review.")
        inv_cols = [c for c in [classified_col, "Confidence", "Value Check"] if c in classified.columns]
        st.dataframe(
            classified[classified["Value Check"].str.startswith("INVALID", na=False)][inv_cols],
            use_container_width=True,
        )
    else:
        st.success("All classifications match the rubric.")

# ═══════════════════════════════════════════════════════════════
# STEP 4 — QA Review
# ═══════════════════════════════════════════════════════════════
elif step == "4 · QA Review":
    page_header("QA Review", "Sample rows for human review and calculate agreement rate.")

    if st.session_state.transcripts is None:
        st.warning("Complete Steps 1–3 first.")
        st.stop()

    df = st.session_state.transcripts
    _, allowed = build_rubric_context(st.session_state.rubric)

    with st.expander("Sampling configuration", expanded=st.session_state.qa_sample is None):
        c1, c2, c3 = st.columns(3)
        confidence = c1.selectbox("Confidence level", ["90%", "95%", "99%"], index=1)
        margin = c2.selectbox("Margin of error", ["±3%", "±5%", "±10%"], index=1)
        method = c3.selectbox("Sampling method", ["Stratified", "Random", "Low-confidence priority"])

        classified_col = get_classified_col(df, allowed)
        classified_n = len(df[df[classified_col].notna() & (df[classified_col] != "")]) if classified_col else 0
        n = required_sample_size(classified_n, confidence, margin)
        if classified_n:
            st.caption(f"Required sample: {n} rows ({n/classified_n*100:.1f}% of {classified_n} classified rows)")

        if st.button("Build sample", type="primary"):
            sample = sample_rows(df, method, n).copy()
            sample["QA Status"] = "pending"
            sample["Reviewer Notes"] = ""
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
    col3.metric("Agreement", f"{agreement:.1f}%" if agreement is not None else "—")

    if agreement is not None:
        if agreement < AGREEMENT_THRESHOLD:
            st.warning(f"Agreement is {agreement:.1f}% — below the {AGREEMENT_THRESHOLD}% threshold. Review more rows or refine the rubric.")
        else:
            st.success(f"Agreement is {agreement:.1f}% — passes the {AGREEMENT_THRESHOLD}% threshold.")

    st.divider()

    dim_cols = [dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed]

    for i, (_, row) in enumerate(sample.iterrows()):
        saved = reviews.get(i, {})
        label = f"Row {i+1}  ·  {str(row.get('Summary', ''))[:70]}"
        if saved.get("status") and saved["status"] != "pending":
            label += f"  [{saved['status']}]"
        with st.expander(label):
            for col in dim_cols:
                if col in row:
                    st.markdown(f"**{col}:** {row[col]}")
            st.markdown(f"**Confidence:** {row.get('Confidence', '')}")
            st.caption(f"AI notes: {row.get('AI Notes', '')}")
            st.markdown("")

            c1, c2 = st.columns([1, 2])
            status = c1.selectbox(
                "Status", ["pending", "approved", "override", "skip"],
                index=["pending", "approved", "override", "skip"].index(saved.get("status", "pending")),
                key=f"status_{i}",
            )
            notes = c2.text_input("Reviewer notes", value=saved.get("notes", ""), key=f"notes_{i}")

            overrides = {}
            if status == "override":
                st.markdown("**Corrections**")
                oc = st.columns(len(dim_cols))
                for j, col in enumerate(dim_cols):
                    overrides[col] = oc[j].text_input(col, value=saved.get(f"o_{col}", ""), key=f"o_{col}_{i}")

            if st.button("Save", key=f"save_{i}"):
                reviews[i] = {"status": status, "notes": notes, **{f"o_{col}": v for col, v in overrides.items()}}
                st.session_state.qa_reviews = reviews
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# STEP 5 — Golden Set  (Recurring only)
# ═══════════════════════════════════════════════════════════════
elif step == "5 · Golden Set":
    page_header("Golden Set", "Promote verified rows to the golden set for future runs.")

    reviews = st.session_state.qa_reviews or {}
    sample = st.session_state.qa_sample
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

    c1, c2, c3 = st.columns(3)
    c1.metric("Existing examples", len(gs["examples"]))
    c2.metric("Past runs", len(gs["runs"]))
    c3.metric("Agreement this run", f"{agreement:.1f}%" if agreement is not None else "—")

    st.divider()

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

    st.markdown(f"### {len(promotable)} rows ready to add")
    if promotable:
        preview_df = pd.DataFrame([{
            "Summary": p["summary"][:80],
            **{k: v for k, v in p["classifications"].items()}
        } for p in promotable])
        st.dataframe(preview_df, use_container_width=True)

    st.markdown("")
    if st.button("Save to golden set", type="primary", disabled=not promotable):
        gs, added = add_examples(gs, promotable)
        gs = record_run(gs, agreement, added)
        st.session_state.golden_set = gs
        st.success(f"Added {added} examples. Golden set now has {len(gs['examples'])} total.")
        st.rerun()

    if gs["runs"]:
        st.divider()
        st.markdown("### Agreement over time")
        runs_df = pd.DataFrame(gs["runs"])
        runs_df = runs_df[runs_df["agreement_rate"].notna()]
        if not runs_df.empty:
            st.line_chart(runs_df.set_index("date")["agreement_rate"], color="#009FD9")
        st.dataframe(pd.DataFrame(gs["runs"]), use_container_width=True, hide_index=True)

    st.divider()
    st.download_button(
        "Download golden set (JSON)",
        export_golden_set(gs),
        file_name=f"{gs['series'].lower().replace(' ', '-')}-golden-set.json",
        mime="application/json",
    )

# ═══════════════════════════════════════════════════════════════
# STEP 5/6 — Report
# ═══════════════════════════════════════════════════════════════
elif step in ("5 · Report", "6 · Report"):
    page_header("Report")

    if st.session_state.transcripts is None:
        st.warning("Complete the previous steps first.")
        st.stop()

    df = st.session_state.transcripts.copy()
    reviews = st.session_state.qa_reviews or {}
    sample = st.session_state.qa_sample
    _, allowed = build_rubric_context(st.session_state.rubric)
    dim_cols = [dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed]

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

    approved = sum(1 for v in reviews.values() if v["status"] == "approved")
    overridden = sum(1 for v in reviews.values() if v["status"] == "override")
    reviewed = approved + overridden
    agreement = f"{approved / reviewed * 100:.1f}%" if reviewed > 0 else "N/A"
    conf_counts = classified["Confidence"].str.lower().value_counts()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total rows", total)
    col2.metric("Reviewed", reviewed)
    col3.metric("Agreement", agreement)
    col4.metric("High confidence", conf_counts.get("high", 0))

    st.divider()

    cols = st.columns(min(len(dim_cols), 2))
    for i, col in enumerate(dim_cols):
        if col not in classified.columns:
            continue
        with cols[i % 2]:
            st.markdown(f"### {col}")
            breakdown = classified[col].value_counts().reset_index()
            breakdown.columns = [col, "Count"]
            breakdown["% of Total"] = (breakdown["Count"] / total * 100).round(1).astype(str) + "%"
            st.dataframe(breakdown, use_container_width=True, hide_index=True)

    if st.session_state.study_type == "Recurring" and st.session_state.golden_set:
        gs = st.session_state.golden_set
        st.divider()
        st.markdown(f"**Golden set:** {gs['series']} · {len(gs['examples'])} examples · {len(gs['runs'])} runs")

    st.divider()
    csv = classified.to_csv(index=False)
    st.download_button("Download results (CSV)", csv, "results.csv", "text/csv")
