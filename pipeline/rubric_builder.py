"""
Rubric builder — generates analysis dimensions from a plain-English description.

Takes a research question like "identify calls that discussed Thumbtack numbers"
and returns a rubric DataFrame ready to drop into the classify pipeline.
"""

import json
import re
import pandas as pd
from pipeline.gemini import call_gemini


SYSTEM_PROMPT = """You are an expert qualitative research analyst at Thumbtack.
Your job is to turn a plain-English research question into a structured analysis rubric.

Rules:
- Generate 3–6 dimensions that together fully answer the research question
- Each dimension should be independently classifiable from the text alone
- Possible values should be mutually exclusive, exhaustive, and lowercase
- Always include "unclear" or "not applicable" as a fallback value where it makes sense
- Keep dimension names short (2–4 words), values even shorter (1–3 words)
- The "What This Measures" description should be one clear sentence

Return ONLY a JSON array, no other text:
[
  {
    "dimension": "short dimension name",
    "values": ["value1", "value2", "value3"],
    "description": "One sentence explaining what this dimension captures."
  }
]"""


def generate_rubric_from_description(
    description: str,
    mode_context: str = "customer support transcripts",
) -> pd.DataFrame:
    """
    Call Gemini to generate rubric dimensions from a plain-English description.
    Returns a DataFrame with columns matching the app's rubric format.
    """
    prompt = f"""{SYSTEM_PROMPT}

Data type being analyzed: {mode_context}

Research question / goal:
{description}

Return ONLY the JSON array."""

    raw = call_gemini(prompt, temperature=0.3)
    cleaned = re.sub(r"```json\n?|```\n?", "", raw).strip()
    dimensions = json.loads(cleaned)

    rows = []
    for d in dimensions:
        rows.append({
            "Dimension Name": d["dimension"].strip().title(),
            "Possible Values (comma-separated)": ", ".join(v.strip().lower() for v in d["values"]),
            "What This Measures": d["description"].strip(),
            "Active?": "yes",
        })
    return pd.DataFrame(rows)


def rubric_from_template(template: dict) -> pd.DataFrame:
    """Convert a settings.py template dict into a rubric DataFrame."""
    rows = []
    for dim in template["dimensions"]:
        rows.append({
            "Dimension Name": dim["name"],
            "Possible Values (comma-separated)": ", ".join(dim["values"]),
            "What This Measures": dim["description"],
            "Active?": "yes",
        })
    return pd.DataFrame(rows)
