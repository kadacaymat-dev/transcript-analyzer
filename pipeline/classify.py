import hashlib
import json
import re
import pandas as pd
from pipeline.gemini import call_gemini


def rubric_hash(rubric_df: pd.DataFrame) -> str:
    """Short hash of the rubric content — used to detect when rows are stale."""
    key = "|".join(
        f"{row.get('Dimension Name', '')}:{row.get('Possible Values (comma-separated)', '')}"
        for _, row in rubric_df.iterrows()
    )
    return hashlib.md5(key.encode()).hexdigest()[:8]


def build_rubric_context(rubric_df: pd.DataFrame) -> tuple[str, dict]:
    context = "ANALYSIS RUBRIC:\n\n"
    allowed = {}

    for _, row in rubric_df.iterrows():
        dimension = str(row.get("Dimension Name", row.get("Dimension", ""))).strip()
        values = str(row.get("Possible Values (comma-separated)", row.get("Possible Values", row.get("Values", "")))).strip()
        description = str(row.get("What This Measures", row.get("Description", ""))).strip()
        active = str(row.get("Active?", "yes")).strip().lower()

        if not dimension or active == "no":
            continue

        context += f"{dimension}:\n  Values: {values}\n  Description: {description}\n\n"
        allowed[dimension] = [v.strip().lower() for v in values.split(",") if v.strip()]

    context += _constraint_block(allowed)
    return context, allowed


def _constraint_block(allowed: dict) -> str:
    block = "\n────────────────────────────────────────\n"
    block += "STRICT OUTPUT CONSTRAINTS:\n"
    block += "Use ONLY these exact values. Output \"unclear\" if nothing fits.\n\n"
    for dim, vals in allowed.items():
        field = dim.lower().replace(" ", "_")
        block += f"  • {field}: {', '.join(vals)}\n"
    block += "  • confidence: high, medium, low\n"
    block += "────────────────────────────────────────\n\n"
    return block


def _build_output_fields(allowed: dict) -> str:
    """Build the JSON field list dynamically from rubric dimensions."""
    lines = []
    for dim in allowed:
        field = dim.lower().replace(" ", "_")
        lines.append(f'- {field}: exact value from STRICT OUTPUT CONSTRAINTS only')
    lines.append('- confidence: exactly "high", "medium", or "low"')
    lines.append('- ai_notes: one sentence summarizing the key finding')
    return "\n".join(lines)


def classify_row(
    rubric_context: str,
    text: str,
    summary: str,
    prompt_context: str = "You are analyzing a text record.",
) -> dict:
    output_fields = _build_output_fields(
        {k: [] for k in _parse_dimensions(rubric_context)}
    )

    prompt = f"""{rubric_context}

{prompt_context} Analyze the record below using the rubric above.

Return ONLY a JSON object with these fields:
{output_fields}

RECORD:
Summary / Context: {summary}
Full Text: {text[:3000]}

Return ONLY valid JSON, no other text."""

    raw = call_gemini(prompt, temperature=0.1)
    cleaned = re.sub(r"```json\n?|```\n?", "", raw).strip()
    return json.loads(cleaned)


def _parse_dimensions(rubric_context: str) -> list[str]:
    """Extract dimension names from the rubric context string."""
    dims = []
    for line in rubric_context.splitlines():
        if line and not line.startswith(" ") and ":" in line and "────" not in line:
            name = line.split(":")[0].strip()
            if name and name not in ("ANALYSIS RUBRIC", "STRICT OUTPUT CONSTRAINTS"):
                dims.append(name)
    return dims


def check_values(result: dict, allowed: dict) -> str:
    issues = []
    for dim, vals in allowed.items():
        field = dim.lower().replace(" ", "_")
        val = result.get(field, "").lower()
        if vals and val and val not in vals:
            issues.append(f'{field}="{result.get(field)}"')
    if result.get("confidence", "").lower() not in ["high", "medium", "low"]:
        issues.append(f'confidence="{result.get("confidence")}"')
    return "OK" if not issues else "INVALID: " + ", ".join(issues)
