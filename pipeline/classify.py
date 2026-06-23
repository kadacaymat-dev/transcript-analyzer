import json
import re
import pandas as pd
from pipeline.gemini import call_gemini


def build_rubric_context(rubric_df: pd.DataFrame) -> tuple[str, dict]:
    context = "CLASSIFICATION RUBRIC:\n\n"
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
    field_map = {
        "Failure Mode": "failure_mode",
        "Escalation Trigger": "escalation_trigger",
    }
    block = "\n────────────────────────────────────────\n"
    block += "STRICT OUTPUT CONSTRAINTS:\n"
    block += "Use ONLY these exact values. Output \"unclear\" if nothing fits.\n\n"
    for dim, vals in allowed.items():
        field = field_map.get(dim, dim.lower().replace(" ", "_"))
        block += f"  • {field}: {', '.join(vals)}\n"
    block += "  • confidence: high, medium, low\n"
    block += "────────────────────────────────────────\n\n"
    return block


def classify_row(rubric_context: str, transcript: str, user_summary: str) -> dict:
    prompt = f"""{rubric_context}

Classify this customer support conversation. Return ONLY a JSON object with:
- intent: 4-9 word phrase describing what the customer was trying to do
- failure_mode: exact value from STRICT OUTPUT CONSTRAINTS only
- escalation_trigger: exact value from STRICT OUTPUT CONSTRAINTS only
- confidence: exactly "high", "medium", or "low"
- ai_notes: one sentence explaining why it escalated

CONVERSATION:
User Request: {user_summary}
Transcript: {transcript[:3000]}

Return ONLY valid JSON, no other text."""

    raw = call_gemini(prompt, temperature=0.1)
    cleaned = re.sub(r"```json\n?|```\n?", "", raw).strip()
    return json.loads(cleaned)


def check_values(result: dict, allowed: dict) -> str:
    issues = []
    fm_allowed = [v.lower() for v in allowed.get("Failure Mode", [])]
    et_allowed = [v.lower() for v in allowed.get("Escalation Trigger", [])]

    if fm_allowed and result.get("failure_mode", "").lower() not in fm_allowed:
        issues.append(f"failure_mode=\"{result.get('failure_mode')}\"")
    if et_allowed and result.get("escalation_trigger", "").lower() not in et_allowed:
        issues.append(f"escalation_trigger=\"{result.get('escalation_trigger')}\"")
    if result.get("confidence", "").lower() not in ["high", "medium", "low"]:
        issues.append(f"confidence=\"{result.get('confidence')}\"")

    return "OK" if not issues else "INVALID: " + ", ".join(issues)
