# Transcript Analyzer

Streamlit app for classifying and QA-reviewing support conversation transcripts using Gemini via Vertex AI.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

Requires GCP credentials with access to `tt-ai-platform`. Run `gcloud auth application-default login` if needed.

## Steps

| Step | What it does |
|------|-------------|
| 1 · Upload Data | Upload transcripts CSV + rubric CSV |
| 2 · Classify | AI classifies each row using the rubric |
| 3 · Validate | Checks all values against rubric allowed lists |
| 4 · QA Review | Statistical sample for human review + agreement score |
| 5 · Report | Breakdown tables + CSV export |

## Required CSV columns

**Transcripts:** `Date`, `Transcript`, `User Request Summary`, `Intent`, `Failure Mode`, `Escalation Trigger`, `Confidence`, `AI Notes`

**Rubric:** `Dimension Name`, `What This Measures`, `Possible Values`, `Active?`
