"""
Chat — natural language Q&A over the loaded transcript dataset.

Two question modes handled automatically:
  1. Counting / filtering  — "how many cases where X"
     Pre-filters with pandas text search, AI confirms from matches.
  2. Semantic / example finding — "show me cases with legal threats"
     Sends compact transcript context to Gemini, returns matching row indices.

Context strategy (fits Gemini 1.5 Flash's 1M-token window):
  - Always includes: row index, Date, Summary (all rows)
  - For rows matching keyword pre-filter: also includes Text (truncated)
  - Cap: 300 rows of full context; beyond that, summaries only + count note
"""

import re
import pandas as pd
from typing import Optional
from pipeline.gemini import call_gemini

MAX_FULL_CONTEXT_ROWS = 300
TEXT_TRUNCATE_CHARS   = 400


def answer_question(
    question: str,
    df: pd.DataFrame,
    history: list,
    rubric_df: Optional[pd.DataFrame] = None,
) -> dict:
    """
    Answer a natural language question about the loaded dataset.

    Returns:
        answer        — str, the AI's response
        matching_rows — Optional[pd.DataFrame], rows the AI cited (for display)
        method        — "keyword" | "semantic" | "pandas_count"
        capped        — bool, True if dataset was truncated for context
    """
    question = question.strip()
    total_rows = len(df)

    # ── 1. Detect question intent ──────────────────────────────────
    intent = _detect_intent(question)

    # ── 2. Pre-filter with pandas for keyword-type questions ────────
    keyword_matches = _pandas_keyword_search(question, df)

    # ── 3. Build context ────────────────────────────────────────────
    context_df, capped = _select_context_rows(df, keyword_matches, intent)
    context_str = _build_context_string(context_df, df, rubric_df)

    # ── 4. Build conversation history for multi-turn ────────────────
    history_str = ""
    if history:
        recent = history[-6:]  # last 3 exchanges
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_str += f"{role}: {msg['content']}\n"

    # ── 5. Call Gemini ───────────────────────────────────────────────
    prompt = _build_prompt(question, context_str, history_str, total_rows, capped, intent)

    try:
        raw = call_gemini(prompt, temperature=0.2)
    except Exception as e:
        return {
            "answer": f"Could not reach AI: {e}",
            "matching_rows": None,
            "method": intent,
            "capped": capped,
        }

    # ── 6. Parse response ────────────────────────────────────────────
    answer, row_indices = _parse_response(raw, df)

    matching_rows = None
    if row_indices:
        valid = [i for i in row_indices if 0 <= i < total_rows]
        if valid:
            matching_rows = df.iloc[valid].copy()
            # Add original row numbers so user can find them in the full table
            matching_rows.insert(0, "Row #", [i + 2 for i in valid])  # +2: header + 1-indexed

    return {
        "answer": answer,
        "matching_rows": matching_rows,
        "method": intent,
        "capped": capped,
    }


# ── Intent detection ─────────────────────────────────────────────

def _detect_intent(question: str) -> str:
    q = question.lower()
    count_signals  = ["how many", "count", "number of", "what %", "what percent", "percentage"]
    find_signals   = ["show me", "find", "examples of", "point me", "which cases", "give me",
                      "any cases", "cases where", "transcripts where", "identify"]
    if any(s in q for s in count_signals):
        return "count"
    if any(s in q for s in find_signals):
        return "find_examples"
    return "semantic"


# ── Pandas keyword pre-filter ────────────────────────────────────

def _pandas_keyword_search(question: str, df: pd.DataFrame) -> list:
    """
    Extract quoted phrases or prominent nouns from the question and
    do a case-insensitive text search across Text and Summary columns.
    Returns list of matching row indices (empty if nothing found).
    """
    # Extract quoted strings first
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', question)
    phrases = [q[0] or q[1] for q in quoted]

    # If no quotes, try to extract meaningful keywords (skip common stopwords)
    if not phrases:
        stopwords = {"how","many","cases","where","the","a","an","in","of","to","is",
                     "are","did","do","does","that","which","there","any","all","show",
                     "me","find","give","point","i","you","we","they","was","were",
                     "based","on","from","with","and","or","not","have","had","has"}
        words = re.findall(r'\b[a-zA-Z]{4,}\b', question)
        phrases = [w for w in words if w.lower() not in stopwords][:3]

    if not phrases:
        return []

    text_cols = [c for c in ["Text", "Summary", "transcript", "conversation"] if c in df.columns]
    if not text_cols:
        return []

    mask = pd.Series([False] * len(df), index=df.index)
    for phrase in phrases:
        for col in text_cols:
            mask |= df[col].astype(str).str.contains(phrase, case=False, na=False, regex=False)

    return list(df.index[mask])


# ── Context building ─────────────────────────────────────────────

def _select_context_rows(
    df: pd.DataFrame,
    keyword_matches: list,
    intent: str,
) -> tuple:
    """
    Choose which rows to include in context.
    Returns (context_df, capped).
    """
    total = len(df)

    if intent in ("find_examples", "count") and keyword_matches:
        # Lead with keyword matches, then fill up to MAX_FULL_CONTEXT_ROWS from the rest
        match_set = set(keyword_matches)
        others = [i for i in df.index if i not in match_set]
        selected = list(keyword_matches) + others
        selected = selected[:MAX_FULL_CONTEXT_ROWS]
        capped = total > MAX_FULL_CONTEXT_ROWS
    elif total <= MAX_FULL_CONTEXT_ROWS:
        selected = list(df.index)
        capped = False
    else:
        # Sample: first 100 + 100 random + last 100 for recency spread
        head  = list(df.index[:100])
        tail  = list(df.index[-100:])
        mid_pool = list(df.index[100:-100])
        import random
        random.seed(42)
        mid = random.sample(mid_pool, min(100, len(mid_pool))) if mid_pool else []
        seen = set()
        selected = [i for i in (head + mid + tail) if not (i in seen or seen.add(i))]
        capped = True

    return df.loc[selected], capped


def _build_context_string(
    context_df: pd.DataFrame,
    full_df: pd.DataFrame,
    rubric_df: Optional[pd.DataFrame],
) -> str:
    lines = []
    # Which columns to show
    text_col    = next((c for c in ["Text", "transcript", "conversation"] if c in context_df.columns), None)
    summary_col = next((c for c in ["Summary", "User Request Summary", "summary"] if c in context_df.columns), None)
    date_col    = next((c for c in ["Date", "date", "created_date"] if c in context_df.columns), None)

    # Classification columns from rubric
    rubric_dims = []
    if rubric_df is not None and "Dimension Name" in rubric_df.columns:
        rubric_dims = [d for d in rubric_df["Dimension Name"].tolist() if d in context_df.columns]

    for pos, (idx, row) in enumerate(context_df.iterrows()):
        parts = [f"[Row {pos + 1}]"]
        if date_col:
            parts.append(f"Date: {row.get(date_col, '')}")
        if summary_col:
            parts.append(f"Summary: {str(row.get(summary_col, ''))[:200]}")
        for dim in rubric_dims:
            if row.get(dim):
                parts.append(f"{dim}: {row[dim]}")
        if text_col:
            text = str(row.get(text_col, ""))
            parts.append(f"Transcript: {text[:TEXT_TRUNCATE_CHARS]}{'...' if len(text) > TEXT_TRUNCATE_CHARS else ''}")
        lines.append("  ".join(parts))

    return "\n".join(lines)


# ── Prompt ───────────────────────────────────────────────────────

def _build_prompt(
    question: str,
    context_str: str,
    history_str: str,
    total_rows: int,
    capped: bool,
    intent: str,
) -> str:
    cap_note = (
        f"\nNote: The dataset has {total_rows} rows total. You are seeing a representative "
        f"sample — exact counts should be treated as estimates.\n"
        if capped else f"\nNote: All {total_rows} rows are shown.\n"
    )

    history_block = f"\nPrevious conversation:\n{history_str}\n" if history_str else ""

    intent_instruction = {
        "count": (
            "The user is asking a counting or quantification question. "
            "Give a direct number or percentage. Cite specific row numbers if the count is small."
        ),
        "find_examples": (
            "The user wants specific examples or cases. "
            "Identify the most relevant rows and reference them by their [Row N] number. "
            "Quote brief excerpts from the transcript to support why each row matches."
        ),
        "semantic": (
            "Answer the question using patterns, themes, or specific evidence from the data. "
            "Reference row numbers when citing specific examples."
        ),
    }.get(intent, "")

    return f"""You are an analyst helping a Thumbtack team member understand their transcript data.
{cap_note}
{history_block}
DATASET ({total_rows} conversations):
{context_str}

QUESTION: {question}

Instructions:
- {intent_instruction}
- Be specific: quote brief excerpts and cite [Row N] numbers.
- If you cannot answer from the data shown, say so clearly — do not guess.
- At the end of your response, on a new line, output a JSON block with this exact format:
  ROWS_JSON: {{"indices": [0, 4, 11]}}
  where the indices are 0-based positions of the rows you cited (or [] if none).
- Keep your answer concise and direct."""


# ── Response parsing ─────────────────────────────────────────────

def _parse_response(raw: str, df: pd.DataFrame) -> tuple:
    """Extract answer text and row indices from the AI response."""
    import json

    row_indices = []
    answer = raw.strip()

    # Find and strip the ROWS_JSON block
    json_match = re.search(r'ROWS_JSON:\s*(\{[^}]*\})', raw, re.DOTALL)
    if json_match:
        answer = raw[:json_match.start()].strip()
        try:
            data = json.loads(json_match.group(1))
            row_indices = [int(i) for i in data.get("indices", []) if str(i).isdigit() or isinstance(i, int)]
        except (json.JSONDecodeError, ValueError):
            pass

    return answer, row_indices
