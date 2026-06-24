import time
import datetime
import pandas as pd
import streamlit as st

from config.settings import AGREEMENT_THRESHOLD, ANALYSIS_MODES, RUBRIC_TEMPLATES
from pipeline.classify import build_rubric_context, classify_row, check_values, rubric_hash
from pipeline.golden_set import (
    new_golden_set, load_golden_set, export_golden_set,
    record_run, add_examples, classify_with_examples,
)
from pipeline.sampling import required_sample_size, sample_rows
from pipeline.bq_connector import fetch_maven_conversations, get_channel_counts, CHANNELS
from pipeline.rubric_builder import generate_rubric_from_description, rubric_from_template
from pipeline.study_profile import (
    new_profile, load_profile, export_profile, profile_filename,
    attach_rubric, rubric_from_profile,
    record_run as profile_record_run,
    add_examples_to_profile, run_history_df,
)

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
    "rubric_version": None,
    "qa_sample": None,
    "qa_reviews": {},
    "t_col_map": None,
    "r_col_map": None,
    "calib_samples": None,    # list of classified sample dicts for calibration round
    "calib_reviews": {},      # {index: "up"|"down"}
    "rubric_draft": None,      # rubric being edited before confirm
    "selected_template": None,
    "study_profile": None,     # active study profile dict
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
        for k in ["study_type", "series_name", "golden_set", "transcripts", "rubric", "qa_sample", "qa_reviews", "calib_samples", "calib_reviews", "rubric_draft", "selected_template", "study_profile"]:
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

if st.session_state.study_profile:
    sp = st.session_state.study_profile
    n_runs = len(sp.get("run_history", []))
    last = sp.get("last_run", "never")
    st.sidebar.divider()
    st.sidebar.markdown(
        f'<div style="font-size:0.75rem;color:#676d73">'
        f'<span style="color:#2F3033;font-weight:600">Study Profile</span><br>'
        f'{n_runs} run{"s" if n_runs != 1 else ""} · last {last}'
        f'</div>',
        unsafe_allow_html=True,
    )

# ═══════════════════════════════════════════════════════════════
# STEP 0 — Study Setup
# ═══════════════════════════════════════════════════════════════
if step == "0 · Study Setup":
    page_header("Study Setup", "Choose how you want to run this analysis.")

    col1, col2, col3 = st.columns(3, gap="large")

    # ── Card 1: Continue a saved study ──────────────────────────
    with col1:
        st.markdown("""
<div class="study-card">
<h3>Continue a saved study</h3>
<p>Pick up where you left off. Your rubric, examples, and run history are all restored — just upload new data and run.</p>
<ul>
<li>Rubric pre-loaded — no setup needed</li>
<li>AI uses all past approved examples</li>
<li>Agreement rate and themes tracked over time</li>
</ul>
</div>
""", unsafe_allow_html=True)
        st.markdown("")
        profile_file = st.file_uploader(
            "Upload study profile (.json)",
            type="json",
            key="profile_upload",
            label_visibility="collapsed",
        )
        if profile_file:
            profile = load_profile(profile_file.read())
            rdf = rubric_from_profile(profile)
            gs = profile.get("golden_set", {})
            n_ex = len(gs.get("examples", []))
            n_runs = len(profile.get("run_history", []))
            last = profile.get("last_run", "never")
            st.info(
                f"**{profile['name']}** · {n_runs} past runs · {n_ex} examples · last run {last}"
            )
            if st.button("Continue this study", use_container_width=True, type="primary", key="btn_continue"):
                st.session_state.study_profile = profile
                st.session_state.study_type = "Recurring"
                st.session_state.series_name = profile["name"]
                st.session_state.analysis_mode = profile.get("analysis_mode", "Transcript Analysis")
                st.session_state.golden_set = gs
                if rdf is not None:
                    st.session_state.rubric = rdf
                    st.session_state.rubric_version = rubric_hash(rdf)
                st.rerun()

    # ── Card 2: New recurring study ──────────────────────────────
    with col2:
        st.markdown("""
<div class="study-card">
<h3>New recurring study</h3>
<p>Builds institutional knowledge over time. Good for monthly studies — CSAT, escalation reviews, contact drivers.</p>
<ul>
<li>Creates a study profile you can reuse each run</li>
<li>AI improves as you approve more examples</li>
<li>Agreement rate tracked across runs</li>
</ul>
</div>
""", unsafe_allow_html=True)
        st.markdown("")
        series = st.text_input("Study name", placeholder="e.g. Commercial Ops Escalations", key="series_input")
        if st.button("Start recurring study", use_container_width=True, type="primary",
                     key="btn_recurring", disabled=not series.strip()):
            profile = new_profile(series.strip(), st.session_state.analysis_mode)
            st.session_state.study_type = "Recurring"
            st.session_state.series_name = series.strip()
            st.session_state.study_profile = profile
            st.session_state.golden_set = profile["golden_set"]
            st.rerun()

    # ── Card 3: Ad-hoc ───────────────────────────────────────────
    with col3:
        st.markdown("""
<div class="study-card">
<h3>Ad-hoc</h3>
<p>Fast and disposable. Good for one-off questions where you don't need to build on past results.</p>
<ul>
<li>No setup — define rubric and run</li>
<li>Optional calibration round to warm up the AI</li>
<li>Export results as CSV when done</li>
</ul>
</div>
""", unsafe_allow_html=True)
        st.markdown("")
        if st.button("Start ad-hoc study", use_container_width=True, type="primary", key="btn_adhoc"):
            st.session_state.study_type = "Ad-hoc"
            st.rerun()

# ═══════════════════════════════════════════════════════════════
# STEP 1 — Upload Data
# ═══════════════════════════════════════════════════════════════
elif step == "1 · Upload Data":
    page_header("Upload Data")
    mode = ANALYSIS_MODES[st.session_state.analysis_mode]

    # Show profile context banner if continuing a saved study
    if st.session_state.study_profile:
        sp = st.session_state.study_profile
        n_runs = len(sp.get("run_history", []))
        n_ex = len(sp.get("golden_set", {}).get("examples", []))
        last = sp.get("last_run", "never")
        st.info(
            f"Continuing **{sp['name']}** — {n_runs} past run{'s' if n_runs != 1 else ''} · "
            f"{n_ex} approved examples · last run {last}"
        )

    gs = st.session_state.golden_set
    if gs and gs.get("mode"):
        st.session_state.analysis_mode = gs["mode"]
        mode = ANALYSIS_MODES[gs["mode"]]
        st.caption(mode["description"])
    else:
        new_mode = st.selectbox("Analysis type", list(ANALYSIS_MODES.keys()),
                                index=list(ANALYSIS_MODES.keys()).index(st.session_state.analysis_mode))
        if new_mode != st.session_state.analysis_mode:
            st.session_state.analysis_mode = new_mode
            st.rerun()
        mode = ANALYSIS_MODES[new_mode]
        st.caption(mode["description"])

    st.markdown("### Data source")
    data_source = st.radio(
        "Where is your data coming from?",
        ["Upload a CSV", "Pull from BigQuery (Maven)"],
        horizontal=True,
        key="data_source_radio",
    )

    if data_source == "Upload a CSV":
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

    else:
        # ── BigQuery: Maven SMS / Chat / Voice ──────────────────
        st.markdown("#### Maven conversation filters")
        st.caption("Pulls from `tt-dp-prod.maven.conversations` + `maven.messages`. Requires GCP access via ADC.")

        bq_col1, bq_col2, bq_col3 = st.columns(3)
        today = datetime.date.today()
        default_start = today - datetime.timedelta(days=30)

        start_date = bq_col1.date_input("Start date", value=default_start, key="bq_start")
        end_date = bq_col2.date_input("End date", value=today, key="bq_end")
        channel = bq_col3.selectbox("Channel", ["all"] + CHANNELS, key="bq_channel")

        bq_col4, bq_col5 = st.columns(2)
        escalated_only = bq_col4.checkbox("Escalated conversations only", value=False, key="bq_escalated")
        row_limit = bq_col5.number_input("Max rows", min_value=10, max_value=2000, value=300, step=50, key="bq_limit")

        if st.button("Check availability", key="bq_check"):
            with st.spinner("Querying BigQuery..."):
                try:
                    counts = get_channel_counts(str(start_date), str(end_date))
                    if counts:
                        count_df = pd.DataFrame([
                            {"Channel": ch, "Conversations": n}
                            for ch, n in counts.items()
                        ])
                        st.dataframe(count_df, use_container_width=True, hide_index=True)
                    else:
                        st.warning("No conversations found for this date range.")
                except Exception as e:
                    st.error(f"BigQuery error: {e}")

        if st.button("Pull conversations", type="primary", key="bq_pull"):
            with st.spinner("Pulling from BigQuery — this may take 10-30 seconds..."):
                try:
                    df = fetch_maven_conversations(
                        channel=channel,
                        start_date=str(start_date),
                        end_date=str(end_date),
                        escalated_only=escalated_only,
                        limit=int(row_limit),
                    )
                    if df.empty:
                        st.warning("No rows returned. Try adjusting the date range or filters.")
                    else:
                        for col in ["Confidence", "AI Notes", "Value Check"]:
                            df[col] = ""
                        st.session_state.transcripts = df
                        st.session_state.t_col_map = {"Text": "Text", "Summary": "Summary", "Date": "Date"}
                        st.success(f"Pulled {len(df)} conversations from BigQuery.")
                        st.rerun()
                except Exception as e:
                    st.error(f"BigQuery error: {e}")

    if st.session_state.transcripts is not None:
        src = "BigQuery" if st.session_state.get("data_source_radio") == "Pull from BigQuery (Maven)" else "file"
        st.success(f"{len(st.session_state.transcripts)} rows loaded from {src}.")
        with st.expander("Preview data"):
            preview_cols = [c for c in ["Date", "channel", "Summary", "was_escalated", "sentiment", "Text"]
                            if c in st.session_state.transcripts.columns]
            st.dataframe(st.session_state.transcripts[preview_cols].head(10), use_container_width=True)

    st.divider()

    st.markdown("### Rubric")
    rubric_source = st.radio(
        "How do you want to define your rubric?",
        ["Describe it in plain English", "Pick a template", "Upload a CSV"],
        horizontal=True,
        key="rubric_source",
    )

    # ── Option A: Plain-English description ─────────────────────
    if rubric_source == "Describe it in plain English":
        st.caption("Describe what you want to find out. The AI will generate the rubric dimensions for you.")

        example_prompts = [
            "Review transcripts and identify calls that had discussion about Thumbtack numbers",
            "Understand what drove contacts this week",
            "Identify why conversations escalated and what the AI failed to handle",
            "Analyze survey comments and identify key pain points and themes",
            "Track which Thumbtack product features were mentioned and how customers reacted",
        ]
        selected_example = st.selectbox(
            "Need inspiration? Pick an example or write your own below:",
            [""] + example_prompts,
            key="rubric_example_pick",
        )

        description = st.text_area(
            "Research question",
            value=selected_example,
            height=100,
            placeholder="e.g. Review the transcripts and identify interactions where customers discussed Thumbtack pricing or credits",
            key="rubric_description",
            label_visibility="collapsed",
        )

        if st.button("Generate rubric", type="primary", key="rubric_generate", disabled=not description.strip()):
            with st.spinner("Generating rubric dimensions..."):
                try:
                    mode_ctx = ANALYSIS_MODES[st.session_state.analysis_mode]["prompt_context"]
                    rdf = generate_rubric_from_description(description.strip(), mode_ctx)
                    st.session_state.rubric_draft = rdf
                except Exception as e:
                    st.error(f"Could not generate rubric: {e}")

    # ── Option B: Template picker ────────────────────────────────
    elif rubric_source == "Pick a template":
        st.caption("Pre-built rubrics for the most common analysis types. Select one to preview and use.")

        tmpl_names = list(RUBRIC_TEMPLATES.keys())
        tmpl_cols = st.columns(min(len(tmpl_names), 3))
        selected_tmpl = st.session_state.get("selected_template")

        for i, key in enumerate(tmpl_names):
            tmpl = RUBRIC_TEMPLATES[key]
            is_active = selected_tmpl == key
            border = "#009FD9" if is_active else "#E9ECED"
            bg = "#f0fafd" if is_active else "#FAFAFA"
            with tmpl_cols[i % 3]:
                st.markdown(
                    f'<div style="border:1.5px solid {border};background:{bg};border-radius:8px;'
                    f'padding:0.75rem;margin-bottom:0.5rem;min-height:90px">'
                    f'<div style="font-size:0.85rem;font-weight:600;color:#2F3033">{tmpl["label"]}</div>'
                    f'<div style="font-size:0.78rem;color:#676d73;margin-top:0.25rem">{tmpl["description"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Select", key=f"tmpl_{key}", use_container_width=True):
                    st.session_state.selected_template = key
                    rdf = rubric_from_template(tmpl)
                    st.session_state.rubric_draft = rdf
                    st.rerun()

    # ── Option C: CSV upload ─────────────────────────────────────
    else:
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
            if st.button("Confirm rubric", type="primary", key="rubric_csv_confirm"):
                rdf = raw_rdf.rename(columns={v: k for k, v in r_map.items()})
                st.session_state.rubric = rdf
                st.session_state.rubric_draft = None
                st.session_state.rubric_version = rubric_hash(rdf)
                st.rerun()

    # ── Inline editor — shown after generate or template select ──
    draft = st.session_state.get("rubric_draft")
    if draft is not None and rubric_source != "Upload a CSV":
        st.markdown("#### Review and edit before confirming")
        st.caption("Add, remove, or edit dimensions and values. Changes here update the rubric before any analysis runs.")

        edited = st.data_editor(
            draft,
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "Dimension Name": st.column_config.TextColumn("Dimension Name", width="medium"),
                "Possible Values (comma-separated)": st.column_config.TextColumn("Possible Values (comma-separated)", width="large"),
                "What This Measures": st.column_config.TextColumn("What This Measures", width="large"),
                "Active?": st.column_config.SelectboxColumn("Active?", options=["yes", "no"], width="small"),
            },
            key="rubric_editor",
        )

        col_confirm, col_reset = st.columns([2, 1])
        with col_confirm:
            if st.button("Confirm rubric", type="primary", key="rubric_draft_confirm"):
                st.session_state.rubric = edited
                st.session_state.rubric_draft = None
                st.session_state.rubric_version = rubric_hash(edited)
                st.rerun()
        with col_reset:
            if st.button("Discard", key="rubric_draft_discard"):
                st.session_state.rubric_draft = None
                st.rerun()

    if st.session_state.rubric is not None:
        st.success(f"{len(st.session_state.rubric)} rubric dimensions confirmed.")
        with st.expander("Preview rubric"):
            st.dataframe(st.session_state.rubric, use_container_width=True)
        if st.button("Edit rubric", key="rubric_reedit"):
            st.session_state.rubric_draft = st.session_state.rubric.copy()
            st.session_state.rubric = None
            st.rerun()

    # ── Calibration round (optional, ad-hoc + recurring first run) ──
    both_loaded = st.session_state.transcripts is not None and st.session_state.rubric is not None
    if both_loaded:
        st.divider()
        st.markdown("### Calibration (optional)")
        st.caption(
            "Run 10 sample rows first. Approve or reject each one — approved rows are injected "
            "as few-shot examples so the AI has better context before the full analysis."
        )

        # Import an existing golden set JSON for one-off context
        with st.expander("Import a golden set from a past study"):
            gs_import = st.file_uploader(
                "Golden set JSON", type="json", key="gs_import",
                label_visibility="collapsed",
            )
            if gs_import:
                imported = load_golden_set(gs_import.read())
                n = len(imported.get("examples", []))
                if st.button(f"Use these {n} examples", key="gs_import_confirm", type="primary"):
                    st.session_state.golden_set = imported
                    st.success(f"Imported {n} examples — will be used in Step 2.")
                    st.rerun()

        calib_done = bool(st.session_state.calib_samples)
        approved_count = sum(1 for v in st.session_state.calib_reviews.values() if v == "up")

        if calib_done:
            st.success(
                f"Calibration complete — {approved_count} of {len(st.session_state.calib_samples)} "
                f"samples approved and ready to inject."
            )
            if st.button("Re-run calibration", key="calib_rerun"):
                st.session_state.calib_samples = None
                st.session_state.calib_reviews = {}
                st.rerun()
        else:
            if st.button("Run 10-sample calibration", type="primary", key="calib_start"):
                rctx, allowed_c = build_rubric_context(st.session_state.rubric)
                mode_c = ANALYSIS_MODES[st.session_state.analysis_mode]
                df_c = st.session_state.transcripts
                sample_c = df_c.sample(min(10, len(df_c)), random_state=42)
                samples_out = []
                prog = st.progress(0)
                for i, (_, row) in enumerate(sample_c.iterrows()):
                    prog.progress((i + 1) / len(sample_c))
                    try:
                        result = classify_row(
                            rctx,
                            str(row.get("Text", "")),
                            str(row.get("Summary", "")),
                            prompt_context=mode_c["prompt_context"],
                        )
                    except Exception as e:
                        result = {"ai_notes": f"ERROR: {e}", "confidence": "low"}
                    samples_out.append({
                        "text": str(row.get("Text", "")),
                        "summary": str(row.get("Summary", "")),
                        "result": result,
                        "allowed": allowed_c,
                    })
                st.session_state.calib_samples = samples_out
                st.session_state.calib_reviews = {}
                prog.empty()
                st.rerun()

        # Review UI — show once samples exist
        if st.session_state.calib_samples:
            reviews_c = st.session_state.calib_reviews
            dim_cols_c = [
                dim.lower().replace(" ", "_").replace("_", " ").title()
                for dim in (st.session_state.calib_samples[0].get("allowed") or {})
            ]
            for i, s in enumerate(st.session_state.calib_samples):
                result = s["result"]
                verdict = reviews_c.get(i)
                border_color = "#2db783" if verdict == "up" else ("#ff5a5f" if verdict == "down" else "#E9ECED")
                st.markdown(
                    f'<div style="border:1.5px solid {border_color};border-radius:8px;'
                    f'padding:0.75rem 1rem;margin-bottom:0.75rem">',
                    unsafe_allow_html=True,
                )
                hdr, vote_col = st.columns([5, 1])
                hdr.markdown(
                    f"**{i+1}.** {s['summary'][:100] or s['text'][:100]}"
                )
                with vote_col:
                    vcol1, vcol2 = st.columns(2)
                    if vcol1.button("Yes", key=f"up_{i}", type="primary" if verdict == "up" else "secondary"):
                        reviews_c[i] = "up"
                        st.session_state.calib_reviews = reviews_c
                        st.rerun()
                    if vcol2.button("No", key=f"dn_{i}"):
                        reviews_c[i] = "down"
                        st.session_state.calib_reviews = reviews_c
                        st.rerun()

                with st.expander("AI output", expanded=False):
                    for col in dim_cols_c:
                        field = col.lower().replace(" ", "_")
                        st.markdown(f"**{col}:** {result.get(field, '—')}")
                    st.markdown(f"**Confidence:** {result.get('confidence', '—')}")
                    if result.get("ai_notes"):
                        st.caption(result["ai_notes"])
                    st.caption(f"Text preview: {s['text'][:300]}")
                st.markdown("</div>", unsafe_allow_html=True)

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
    current_version = st.session_state.rubric_version or rubric_hash(st.session_state.rubric)

    unclassified = df[df[classified_col].isna() | (df[classified_col] == "")] if classified_col else df

    # Detect stale rows — classified with a different rubric version
    stale = pd.DataFrame()
    if classified_col and "Rubric Version" in df.columns:
        stale = df[
            df[classified_col].notna() & (df[classified_col] != "") &
            (df["Rubric Version"] != current_version)
        ]

    gs = st.session_state.golden_set
    examples = gs.get("examples", []) if gs else []

    # Merge calibration-approved rows as in-session examples (ad-hoc + recurring)
    calib_examples = []
    if st.session_state.calib_samples:
        for i, s in enumerate(st.session_state.calib_samples):
            if st.session_state.calib_reviews.get(i) == "up":
                clf = {
                    k.lower().replace(" ", "_"): v
                    for k, v in s["result"].items()
                    if k not in ("ai_notes", "confidence")
                }
                clf["confidence"] = s["result"].get("confidence", "")
                calib_examples.append({
                    "text": s["text"],
                    "summary": s["summary"],
                    "classifications": clf,
                })
    all_examples = calib_examples + examples

    c1, c2, c3 = st.columns(3)
    c1.markdown(f'<div class="stat-label">Unanalyzed</div><div class="stat-value">{len(unclassified)}</div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="stat-label">Analyzed</div><div class="stat-value">{len(df) - len(unclassified)}</div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="stat-label">Rubric version</div><div class="stat-value" style="font-size:1rem;font-family:monospace">{current_version}</div>', unsafe_allow_html=True)

    if len(stale) > 0:
        st.warning(
            f"{len(stale)} rows were classified with an older rubric version. "
            f"Run analysis to update them, or skip to keep existing results."
        )

    st.markdown("")
    if all_examples:
        calib_n = len(calib_examples)
        golden_n = len(examples)
        parts = []
        if calib_n:
            parts.append(f"{calib_n} calibration")
        if golden_n:
            parts.append(f"{golden_n} golden set")
        st.info(f"{' + '.join(parts)} examples will be injected into the prompt to improve accuracy.")
    elif st.session_state.study_type == "Recurring":
        st.info("No golden examples yet. This first run will build them after QA review.")

    st.markdown("")

    run_target = st.radio(
        "Which rows to analyze",
        ["Unanalyzed only", "Stale rows (rubric changed)", "All rows"],
        horizontal=True,
        disabled=(len(stale) == 0 and True),
    ) if len(stale) > 0 else "Unanalyzed only"

    if st.button("Run analysis", type="primary"):
        progress = st.progress(0)
        status = st.empty()
        errors = 0
        prompt_context = mode["prompt_context"]
        use_examples = len(all_examples) > 0

        if run_target == "Stale rows (rubric changed)":
            target_df = stale
        elif run_target == "All rows":
            target_df = df
        else:
            target_df = unclassified

        if "Rubric Version" not in df.columns:
            df["Rubric Version"] = ""

        indices = target_df.index.tolist()
        for i, idx in enumerate(indices):
            row = df.loc[idx]
            status.text(f"Analyzing row {i + 1} of {len(indices)}")
            try:
                if use_examples:
                    result = classify_with_examples(
                        rubric_context, all_examples,
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
                df.at[idx, "Rubric Version"] = current_version
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
    seen = set()
    display_cols = [c for c in display_cols if c in df.columns and not (seen.add(c) or c in seen)]
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

    # Confidence calibration chart
    if reviewed >= 5:
        st.markdown("### Confidence calibration")
        st.caption("How well did the AI's confidence score predict actual accuracy?")
        calib_data = []
        for i, (_, row) in enumerate(sample.iterrows()):
            r = reviews.get(i, {})
            if r.get("status") in ("approved", "override"):
                calib_data.append({
                    "confidence": str(row.get("Confidence", "unknown")).lower(),
                    "correct": r["status"] == "approved",
                })
        if calib_data:
            calib_df = pd.DataFrame(calib_data)
            summary = (
                calib_df.groupby("confidence")["correct"]
                .agg(["sum", "count"])
                .rename(columns={"sum": "Approved", "count": "Reviewed"})
                .reset_index()
            )
            summary["Accuracy"] = (summary["Approved"] / summary["Reviewed"] * 100).round(1)
            summary["confidence"] = pd.Categorical(summary["confidence"], ["high", "medium", "low"])
            summary = summary.sort_values("confidence").rename(columns={"confidence": "Confidence"})
            st.dataframe(
                summary[["Confidence", "Reviewed", "Approved", "Accuracy"]],
                use_container_width=True, hide_index=True,
            )
            st.bar_chart(summary.set_index("Confidence")["Accuracy"], color="#009FD9")

    st.divider()

    dim_cols = [dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed]

    for i, (_, row) in enumerate(sample.iterrows()):
        saved = reviews.get(i, {})
        label = f"Row {i+1}  ·  {str(row.get('Summary', ''))[:70]}"
        if saved.get("status") and saved["status"] != "pending":
            label += f"  [{saved['status']}]"
        with st.expander(label):
            # Side-by-side diff view
            ai_col, override_col = st.columns(2)
            with ai_col:
                st.markdown('<div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#676d73;margin-bottom:0.5rem">AI output</div>', unsafe_allow_html=True)
                for col in dim_cols:
                    if col in row:
                        st.markdown(f"**{col}:** {row[col]}")
                st.markdown(f"**Confidence:** {row.get('Confidence', '')}")
                st.caption(f"Notes: {row.get('AI Notes', '')}")

            with override_col:
                st.markdown('<div style="font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;color:#676d73;margin-bottom:0.5rem">Human review</div>', unsafe_allow_html=True)
                status = st.selectbox(
                    "Status", ["pending", "approved", "override", "skip"],
                    index=["pending", "approved", "override", "skip"].index(saved.get("status", "pending")),
                    key=f"status_{i}",
                )
                notes = st.text_input("Notes", value=saved.get("notes", ""), key=f"notes_{i}")

                overrides = {}
                if status == "override":
                    st.markdown('<div style="font-size:0.8rem;color:#676d73;margin-top:0.5rem">Corrections</div>', unsafe_allow_html=True)
                    for col in dim_cols:
                        ai_val = str(row.get(col, ""))
                        override_val = saved.get(f"o_{col}", "")
                        field = st.text_input(
                            col,
                            value=override_val or ai_val,
                            key=f"o_{col}_{i}",
                        )
                        # Highlight if changed from AI value
                        if field and field != ai_val:
                            st.markdown(f'<div style="font-size:0.72rem;color:#009FD9">Changed from: {ai_val}</div>', unsafe_allow_html=True)
                        overrides[col] = field

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

    # ── Study Profile: save run + download ───────────────────────
    st.divider()
    profile = st.session_state.study_profile

    if profile is not None or st.session_state.study_type == "Recurring":
        st.markdown("### Save study profile")
        st.caption(
            "Download the updated profile to use next time. It contains your rubric, all approved "
            "examples, and the full run history — upload it at Step 0 to continue this study."
        )

        agreement_val = (approved / reviewed * 100) if reviewed > 0 else None
        top_themes = {}
        if dim_cols and dim_cols[0] in classified.columns:
            top_themes = classified[dim_cols[0]].value_counts().head(5).to_dict()

        # Build / update the profile
        if profile is None:
            profile = new_profile(
                st.session_state.series_name or "Untitled Study",
                st.session_state.analysis_mode,
            )

        # Attach current rubric
        if st.session_state.rubric is not None:
            profile = attach_rubric(profile, st.session_state.rubric)

        # Promote QA-approved rows into profile's golden set
        dim_cols_lower = [dim.lower().replace(" ", "_").replace("_", " ").title() for dim in allowed]
        promotable = []
        if sample is not None:
            for i, (orig_idx, row) in enumerate(sample.iterrows()):
                r = reviews.get(i, {})
                if r.get("status") not in ("approved", "override"):
                    continue
                clf = {}
                for col in dim_cols_lower:
                    field = col.lower().replace(" ", "_")
                    clf[field] = r.get(f"o_{col}") or str(row.get(col, ""))
                clf["confidence"] = str(row.get("Confidence", ""))
                promotable.append({
                    "text": str(row.get("Text", "")),
                    "summary": str(row.get("Summary", "")),
                    "classifications": clf,
                })

        profile, added = add_examples_to_profile(profile, promotable)
        profile = profile_record_run(profile, total, agreement_val, top_themes, added)
        st.session_state.study_profile = profile

        # Run history chart
        hist_df = run_history_df(profile)
        if len(hist_df) > 1:
            st.markdown("#### Agreement rate over time")
            valid = hist_df[hist_df["agreement_rate"].notna()]
            if not valid.empty:
                st.line_chart(valid.set_index("date")["agreement_rate"], color="#009FD9")

        if len(hist_df) >= 1:
            st.markdown("#### Run history")
            st.dataframe(
                hist_df[["date", "rows_analyzed", "agreement_rate", "examples_added"]].rename(columns={
                    "date": "Date", "rows_analyzed": "Rows", "agreement_rate": "Agreement %",
                    "examples_added": "Examples Added",
                }),
                use_container_width=True, hide_index=True,
            )

        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                "Download study profile (.json)",
                export_profile(profile),
                file_name=profile_filename(profile),
                mime="application/json",
                type="primary",
            )
        with dl_col2:
            csv = classified.to_csv(index=False)
            st.download_button("Download results (.csv)", csv, "results.csv", "text/csv")

        # BQ stub
        st.markdown("")
        st.markdown(
            '<div style="border:1px dashed #d3d4d5;border-radius:8px;padding:0.75rem 1rem;background:#FAFAFA">'
            '<div style="font-size:0.8rem;font-weight:600;color:#676d73">Coming soon — Team Study Library</div>'
            '<div style="font-size:0.78rem;color:#676d73;margin-top:0.25rem">'
            'Once deployed on Data Apps, study profiles will be saved automatically to BigQuery so your '
            'whole team can access them — no file uploads needed.'
            '</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.divider()
        csv = classified.to_csv(index=False)
        st.download_button("Download results (.csv)", csv, "results.csv", "text/csv")
