GCP_PROJECT_ID = "tt-ai-platform"
LOCATION = "us-central1"
MODEL = "gemini-1.5-flash"

VERTEX_URL = (
    f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{GCP_PROJECT_ID}"
    f"/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
)

CLASSIFICATION_COLUMNS = [
    "Theme",
    "Sub-theme",
    "Sentiment",
    "Confidence",
    "AI Notes",
    "Value Check",
]

CONFIDENCE_LEVELS = ["high", "medium", "low"]
AGREEMENT_THRESHOLD = 80

# Each mode defines:
#   label        — display name
#   description  — shown as helper text
#   text_fields  — {internal_name: [autodetect keywords]} for column mapper
#   prompt_context — how the AI prompt describes what it's analyzing
ANALYSIS_MODES = {
    "Transcript Analysis": {
        "label": "Transcript Analysis",
        "description": "Classify support or sales conversations — escalation patterns, failure modes, intents.",
        "text_fields": {
            "Text":    ["transcript", "conversation", "chat", "body", "message"],
            "Summary": ["summary", "request", "user request", "description", "issue"],
            "Date":    ["date", "created", "timestamp", "time"],
        },
        "prompt_context": "You are analyzing a customer support conversation transcript.",
    },
    "Survey / CSAT": {
        "label": "Survey / CSAT",
        "description": "Identify themes, sentiment patterns, and drivers in CSAT or DSAT survey comments.",
        "text_fields": {
            "Text":    ["comment", "response", "feedback", "answer", "text", "verbatim"],
            "Summary": ["question", "prompt", "topic", "category"],
            "Date":    ["date", "submitted", "timestamp", "created"],
        },
        "prompt_context": "You are analyzing a customer survey response or feedback comment.",
    },
    "Case Summaries": {
        "label": "Case Summaries",
        "description": "Find patterns across auto-generated or manual case summaries.",
        "text_fields": {
            "Text":    ["summary", "description", "notes", "details", "body"],
            "Summary": ["title", "subject", "topic", "category", "type"],
            "Date":    ["date", "opened", "created", "timestamp"],
        },
        "prompt_context": "You are analyzing a support case summary.",
    },
    "Custom": {
        "label": "Custom",
        "description": "Analyze any text data. You define the rubric and the AI follows it.",
        "text_fields": {
            "Text":    ["text", "body", "content", "message", "response"],
            "Summary": ["title", "summary", "description", "label"],
            "Date":    ["date", "created", "timestamp", "time"],
        },
        "prompt_context": "You are analyzing a text record.",
    },
}
