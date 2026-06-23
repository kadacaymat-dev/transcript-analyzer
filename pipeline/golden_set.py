import json
import re
from datetime import date
from pipeline.gemini import call_gemini


def new_golden_set(series: str, mode_key: str) -> dict:
    return {"series": series, "mode": mode_key, "runs": [], "examples": []}


def load_golden_set(uploaded_bytes: bytes) -> dict:
    return json.loads(uploaded_bytes.decode("utf-8"))


def export_golden_set(golden_set: dict) -> str:
    return json.dumps(golden_set, indent=2, default=str)


def record_run(golden_set: dict, agreement_pct: float | None, examples_added: int) -> dict:
    golden_set["runs"].append({
        "date": str(date.today()),
        "agreement_rate": round(agreement_pct, 1) if agreement_pct else None,
        "examples_added": examples_added,
        "total_examples": len(golden_set["examples"]),
    })
    return golden_set


def add_examples(golden_set: dict, rows: list[dict]) -> tuple[dict, int]:
    """
    Promote a list of verified rows into the golden set.
    Each row: {text, summary, classifications (dict of field→value)}
    Deduplicates by text content.
    """
    existing_texts = {e["text"] for e in golden_set["examples"]}
    added = 0
    for row in rows:
        if row["text"] in existing_texts:
            continue
        golden_set["examples"].append({
            "text": row["text"],
            "summary": row["summary"],
            "classifications": row["classifications"],
            "run_date": str(date.today()),
            "source": "human_verified",
        })
        existing_texts.add(row["text"])
        added += 1
    return golden_set, added


def classify_with_examples(
    rubric_context: str,
    examples: list[dict],
    text: str,
    summary: str,
    prompt_context: str,
    max_examples: int = 10,
) -> dict:
    """Classify a row using few-shot examples from the golden set."""
    example_block = ""
    if examples:
        sample = examples[-max_examples:]  # use most recent examples
        lines = []
        for i, ex in enumerate(sample):
            clf = ", ".join(f'{k}="{v}"' for k, v in ex["classifications"].items())
            lines.append(
                f"Example {i+1}:\n"
                f"  Summary: {ex['summary']}\n"
                f"  Text snippet: {ex['text'][:300]}\n"
                f"  ✅ Correct classification: {clf}"
            )
        example_block = (
            "\nHUMAN-VERIFIED EXAMPLES — use these to calibrate your output:\n\n"
            + "\n\n".join(lines)
            + "\n"
        )

    # Build dynamic output fields from rubric constraint block
    fields = _parse_fields_from_rubric(rubric_context)
    field_lines = "\n".join(f"- {f}: exact value from STRICT OUTPUT CONSTRAINTS only" for f in fields)
    field_lines += '\n- confidence: exactly "high", "medium", or "low"'
    field_lines += "\n- ai_notes: one sentence summarizing the key finding"

    prompt = f"""{rubric_context}{example_block}
{prompt_context} Analyze the record below using the rubric and examples above.

Return ONLY a JSON object with these fields:
{field_lines}

RECORD:
Summary / Context: {summary}
Full Text: {text[:3000]}

Return ONLY valid JSON, no other text."""

    raw = call_gemini(prompt, temperature=0.1)
    cleaned = re.sub(r"```json\n?|```\n?", "", raw).strip()
    return json.loads(cleaned)


def _parse_fields_from_rubric(rubric_context: str) -> list[str]:
    fields = []
    for line in rubric_context.splitlines():
        if line and not line.startswith(" ") and ":" in line and "────" not in line:
            name = line.split(":")[0].strip()
            if name and name not in ("ANALYSIS RUBRIC", "STRICT OUTPUT CONSTRAINTS"):
                fields.append(name.lower().replace(" ", "_"))
    return fields
