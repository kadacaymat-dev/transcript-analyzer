"""
Study Profile — portable bundle that gives a study its memory.

Bundles together everything needed to resume or repeat an analysis:
  - study metadata (name, mode, description, dates)
  - rubric (so you never have to recreate it)
  - golden set (approved examples that improve the AI each run)
  - run history (agreement rates, volumes, top themes over time)

Saved as a single JSON file. The user downloads it at the end of each
run and uploads it at the start of the next — no database needed.

BQ persistence (team-shared study library) is stubbed here for when
the app is deployed on Data Apps / Cloud Run.
"""

import json
import pandas as pd
from datetime import date
from typing import Optional


PROFILE_VERSION = "1.0"


def new_profile(
    name: str,
    analysis_mode: str,
    description: str = "",
) -> dict:
    return {
        "version": PROFILE_VERSION,
        "name": name,
        "analysis_mode": analysis_mode,
        "description": description,
        "created_at": str(date.today()),
        "last_run": None,
        "rubric": [],          # list of dicts — rubric rows
        "golden_set": {
            "series": name,
            "mode": analysis_mode,
            "examples": [],
            "runs": [],
        },
        "run_history": [],     # lightweight per-run summary for trending
    }


def load_profile(uploaded_bytes: bytes) -> dict:
    return json.loads(uploaded_bytes.decode("utf-8"))


def export_profile(profile: dict) -> str:
    return json.dumps(profile, indent=2, default=str)


def profile_filename(profile: dict) -> str:
    slug = profile["name"].lower().replace(" ", "-").replace("/", "-")
    return f"{slug}-study-profile.json"


def attach_rubric(profile: dict, rubric_df: pd.DataFrame) -> dict:
    """Store the rubric inside the profile."""
    profile["rubric"] = rubric_df.to_dict(orient="records")
    return profile


def rubric_from_profile(profile: dict) -> Optional[pd.DataFrame]:
    """Restore the rubric DataFrame from a profile, or None if not set."""
    rows = profile.get("rubric", [])
    if not rows:
        return None
    return pd.DataFrame(rows)


def record_run(
    profile: dict,
    rows_analyzed: int,
    agreement_pct: Optional[float],
    top_themes: Optional[dict] = None,
    examples_added: int = 0,
) -> dict:
    """Append a run summary and update last_run date."""
    profile["run_history"].append({
        "date": str(date.today()),
        "rows_analyzed": rows_analyzed,
        "agreement_rate": round(agreement_pct, 1) if agreement_pct is not None else None,
        "examples_added": examples_added,
        "top_themes": top_themes or {},
    })
    profile["last_run"] = str(date.today())

    # Keep golden_set runs in sync
    gs = profile.get("golden_set", {})
    gs.setdefault("runs", []).append({
        "date": str(date.today()),
        "agreement_rate": round(agreement_pct, 1) if agreement_pct is not None else None,
        "examples_added": examples_added,
        "total_examples": len(gs.get("examples", [])),
    })
    profile["golden_set"] = gs
    return profile


def add_examples_to_profile(profile: dict, rows: list) -> tuple:
    """
    Add verified rows to the profile's golden set.
    Returns (updated_profile, count_added).
    Deduplicates by text content.
    """
    gs = profile.setdefault("golden_set", {"examples": [], "runs": []})
    existing = {e["text"] for e in gs.get("examples", [])}
    added = 0
    for row in rows:
        if row["text"] in existing:
            continue
        gs["examples"].append({
            "text": row["text"],
            "summary": row["summary"],
            "classifications": row["classifications"],
            "run_date": str(date.today()),
            "source": "human_verified",
        })
        existing.add(row["text"])
        added += 1
    profile["golden_set"] = gs
    return profile, added


def run_history_df(profile: dict) -> pd.DataFrame:
    rows = profile.get("run_history", [])
    if not rows:
        return pd.DataFrame(columns=["date", "rows_analyzed", "agreement_rate", "examples_added"])
    return pd.DataFrame(rows)


# ── BQ persistence stub ──────────────────────────────────────────────────────
# These functions are placeholders for when the app is deployed on Data Apps.
# They will read/write study profiles to a BQ table so the whole team shares
# one study library without managing JSON files.

def list_saved_studies_from_bq() -> list:
    """[Coming soon] List all study profiles saved to BQ."""
    raise NotImplementedError(
        "BQ study library is available after deployment on Thumbtack Data Apps. "
        "For now, use the download/upload JSON workflow."
    )


def save_profile_to_bq(profile: dict) -> None:
    """[Coming soon] Upsert a study profile to tt-dp-prod.maven.text_analyzer_studies."""
    raise NotImplementedError(
        "BQ study library is available after deployment on Thumbtack Data Apps."
    )


def load_profile_from_bq(study_name: str) -> dict:
    """[Coming soon] Load a study profile by name from BQ."""
    raise NotImplementedError(
        "BQ study library is available after deployment on Thumbtack Data Apps."
    )
