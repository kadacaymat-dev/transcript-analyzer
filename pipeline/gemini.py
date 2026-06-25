import requests
import google.auth
import google.auth.transport.requests
from config.settings import VERTEX_URL, GEMINI_API_URL, GEMINI_API_KEY


def _get_token() -> str:
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


def _extract_text(data: dict) -> str:
    return data["candidates"][0]["content"]["parts"][0]["text"]


def call_gemini(prompt: str, temperature: float = 0.1) -> str:
    """
    Call Gemini. Tries Vertex AI first; falls back to the Gemini API key
    if Vertex AI returns 403 (no aiplatform.user access on tt-ai-platform).

    In production on Data Apps the service account has Vertex AI access,
    so the fallback is never reached. Locally, paste GEMINI_API_KEY in
    config/settings.py to unblock development.
    """
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }

    # ── Try Vertex AI first ──────────────────────────────────────
    try:
        token = _get_token()
        resp = requests.post(
            VERTEX_URL,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code == 403:
            raise PermissionError("Vertex AI 403")
        resp.raise_for_status()
        return _extract_text(resp.json())

    except PermissionError:
        pass  # fall through to API key

    # ── Fallback: Gemini API key ─────────────────────────────────
    if not GEMINI_API_KEY or GEMINI_API_KEY == "":
        raise RuntimeError(
            "Vertex AI returned 403 (no tt-ai-platform access) and no GEMINI_API_KEY is set.\n\n"
            "To fix locally: get a free key at https://aistudio.google.com/app/apikey "
            "and paste it into config/settings.py → GEMINI_API_KEY.\n\n"
            "In production (Data Apps), this works automatically via the service account."
        )

    resp = requests.post(
        f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
        headers={"Content-Type": "application/json"},
        json=payload,
    )
    resp.raise_for_status()
    return _extract_text(resp.json())
