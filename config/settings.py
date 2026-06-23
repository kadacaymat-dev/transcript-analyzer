GCP_PROJECT_ID = "tt-ai-platform"
LOCATION = "us-central1"
MODEL = "gemini-1.5-flash"

VERTEX_URL = (
    f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{GCP_PROJECT_ID}"
    f"/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
)

REQUIRED_COLUMNS = [
    "Date",
    "Transcript",
    "User Request Summary",
]

CLASSIFICATION_COLUMNS = [
    "Intent",
    "Failure Mode",
    "Escalation Trigger",
    "Confidence",
    "AI Notes",
    "Value Check",
]

CONFIDENCE_LEVELS = ["high", "medium", "low"]
AGREEMENT_THRESHOLD = 80
