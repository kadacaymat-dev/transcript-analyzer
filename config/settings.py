GCP_PROJECT_ID = "tt-ai-platform"
LOCATION = "us-central1"
MODEL = "gemini-1.5-flash"

# ── AI connection ─────────────────────────────────────────────────
#
# Option 1 — Vertex AI (default, works in production on Data Apps)
#   Requires tt-ai-platform access via service account. Works automatically
#   once deployed. Blocked locally if your account lacks aiplatform.user.
#
# Option 2 — Gemini API key (fallback for local development)
#   Get a free key at: https://aistudio.google.com/app/apikey
#   Paste it below. The app tries Vertex AI first; if it gets a 403 it
#   automatically falls back to the API key.
#
GEMINI_API_KEY = ""   # ← paste your key here for local dev; leave empty in production

VERTEX_URL = (
    f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{GCP_PROJECT_ID}"
    f"/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
)
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
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

# Pre-built rubric templates — each has a name, description, best-fit mode, and dimensions list
RUBRIC_TEMPLATES = {
    "Contact Driver": {
        "label": "Contact Driver Analysis",
        "description": "What drove customers or pros to reach out this week? Categorize the primary reason for contact.",
        "mode": "Transcript Analysis",
        "example_prompt": "Understand what drove contacts this week",
        "dimensions": [
            {
                "name": "Contact Driver",
                "values": ["billing / charges", "account issue", "lead quality", "technical issue", "policy question", "dispute / refund", "general inquiry", "other"],
                "description": "The primary reason the customer or pro reached out.",
            },
            {
                "name": "User Type",
                "values": ["customer", "pro", "unclear"],
                "description": "Whether the contact came from a customer or a Thumbtack pro.",
            },
            {
                "name": "Resolution",
                "values": ["resolved", "escalated", "unresolved", "unclear"],
                "description": "Whether the issue was resolved during the interaction.",
            },
            {
                "name": "Sentiment",
                "values": ["positive", "neutral", "frustrated", "angry"],
                "description": "Overall emotional tone of the contact.",
            },
        ],
    },
    "Escalation Patterns": {
        "label": "Escalation Pattern Analysis",
        "description": "Why are conversations escalating to a live agent? Identify triggers and failure modes.",
        "mode": "Transcript Analysis",
        "example_prompt": "Identify why conversations escalated and what the AI failed to handle",
        "dimensions": [
            {
                "name": "Escalation Trigger",
                "values": ["explicit request", "repeated misunderstanding", "complex issue", "emotional distress", "policy limitation", "technical failure", "unclear"],
                "description": "What caused the conversation to escalate to a human agent.",
            },
            {
                "name": "AI Failure Mode",
                "values": ["wrong answer", "loop / repetition", "missing knowledge", "tone mismatch", "no failure", "unclear"],
                "description": "How the AI bot fell short before escalation.",
            },
            {
                "name": "Issue Category",
                "values": ["billing", "account", "leads", "reviews", "technical", "policy", "other"],
                "description": "The subject matter of the escalated conversation.",
            },
            {
                "name": "Avoidable",
                "values": ["yes", "no", "unclear"],
                "description": "Whether the escalation could have been prevented with a better AI response.",
            },
        ],
    },
    "CSAT Pain Points": {
        "label": "CSAT / Survey Pain Point Analysis",
        "description": "What are customers complaining or praising about? Surface themes from survey comments.",
        "mode": "Survey / CSAT",
        "example_prompt": "Identify key pain points and themes in recent survey comments",
        "dimensions": [
            {
                "name": "Primary Theme",
                "values": ["pricing", "lead quality", "customer service", "product / ux", "pro quality", "communication", "billing", "other"],
                "description": "The main topic the respondent is commenting on.",
            },
            {
                "name": "Sentiment",
                "values": ["positive", "negative", "mixed", "neutral"],
                "description": "The overall tone of the feedback.",
            },
            {
                "name": "Actionability",
                "values": ["specific and actionable", "vague", "praise only", "unclear"],
                "description": "How actionable the feedback is for the product or ops team.",
            },
        ],
    },
    "Thumbtack Numbers": {
        "label": "Thumbtack Numbers Discussion",
        "description": "Did the conversation include discussion of specific Thumbtack numbers — pricing, credits, stats, or metrics?",
        "mode": "Transcript Analysis",
        "example_prompt": "Identify calls that had discussion about Thumbtack numbers",
        "dimensions": [
            {
                "name": "Numbers Discussed",
                "values": ["yes", "no", "unclear"],
                "description": "Whether any specific Thumbtack numbers were mentioned in the conversation.",
            },
            {
                "name": "Number Type",
                "values": ["lead pricing", "credits / refunds", "account stats", "platform metrics", "not applicable"],
                "description": "What category of numbers came up.",
            },
            {
                "name": "Customer Reaction",
                "values": ["accepted", "disputed", "confused", "not applicable"],
                "description": "How the customer responded to the numbers discussed.",
            },
        ],
    },
    "Feature Mentions": {
        "label": "Feature & Product Mention Tracker",
        "description": "Which Thumbtack features or product areas came up in the conversation?",
        "mode": "Transcript Analysis",
        "example_prompt": "Track which product features or areas were mentioned",
        "dimensions": [
            {
                "name": "Feature Area",
                "values": ["leads / targeting", "payments", "reviews", "profile", "messaging", "background check", "app / technical", "other", "none"],
                "description": "The Thumbtack product area mentioned in the conversation.",
            },
            {
                "name": "Mention Type",
                "values": ["complaint", "question", "praise", "informational", "not applicable"],
                "description": "How the feature was brought up.",
            },
            {
                "name": "Outcome",
                "values": ["resolved", "referred to help center", "escalated", "not applicable"],
                "description": "How the feature-related discussion was handled.",
            },
        ],
    },
    "EPO Churn Analysis": {
        "label": "EPO Churn Analysis",
        "description": "Analyze Early Pro Onboarding transcripts to understand why pros churn within 28 or 60 days of their first Sales & Success call.",
        "mode": "Transcript Analysis",
        "example_prompt": "Understand why newly onboarded pros churn within 28 days of their EPO call",
        "dimensions": [
            {
                "name": "Churn Signal",
                "values": ["explicit intent to leave", "dissatisfaction expressed", "disengaged / unresponsive", "positive / interested", "neutral", "unclear"],
                "description": "Whether the transcript contains language or behavior that predicts churn.",
            },
            {
                "name": "Primary Concern",
                "values": ["lead quality / quantity", "pricing / credits", "not enough work", "platform confusion", "competition / alternatives", "no concern raised", "other"],
                "description": "The main concern or objection the pro raised during the EPO interaction.",
            },
            {
                "name": "Rep Action",
                "values": ["addressed concern effectively", "offered support / resources", "scheduled follow-up", "closed / converted", "no meaningful action", "could not reach pro"],
                "description": "What the Sales & Success rep did to address the pro's situation.",
            },
            {
                "name": "Pro Engagement",
                "values": ["high — full conversation", "medium — partial engagement", "low — brief / distracted", "no contact"],
                "description": "How engaged the pro was during the EPO interaction.",
            },
        ],
    },
}

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
