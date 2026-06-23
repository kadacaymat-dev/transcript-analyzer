import math
import pandas as pd


Z_SCORES = {"90%": 1.645, "95%": 1.96, "99%": 2.576}
MARGIN_MAP = {"±3%": 0.03, "±5%": 0.05, "±10%": 0.10}


def required_sample_size(n: int, confidence: str = "95%", margin: str = "±5%") -> int:
    z = Z_SCORES.get(confidence, 1.96)
    e = MARGIN_MAP.get(margin, 0.05)
    p = 0.5
    n_unbounded = (z * z * p * (1 - p)) / (e * e)
    if n == 0:
        return math.ceil(n_unbounded)
    return math.ceil(n_unbounded / (1 + (n_unbounded - 1) / n))


def sample_rows(df: pd.DataFrame, method: str, sample_size: int) -> pd.DataFrame:
    classified = df[df["Intent"].notna() & (df["Intent"] != "")]

    if method == "Stratified":
        frames = []
        for conf in ["high", "medium", "low"]:
            group = classified[classified["Confidence"].str.lower() == conf]
            quota = math.ceil((len(group) / len(classified)) * sample_size)
            frames.append(group.sample(min(quota, len(group))))
        return pd.concat(frames).drop_duplicates()

    if method == "Low-confidence priority":
        low = classified[classified["Confidence"].str.lower() == "low"]
        rest = classified[classified["Confidence"].str.lower() != "low"]
        remaining = max(0, sample_size - len(low))
        return pd.concat([low, rest.sample(min(remaining, len(rest)))]).drop_duplicates()

    # Random
    return classified.sample(min(sample_size, len(classified)))
