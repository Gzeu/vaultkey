"""
prefix_detect.py — Auto-detect API service from key prefix and mask key for display.

The PREFIX_MAP is ordered from longest to shortest prefix to avoid false-positives
(e.g., 'sk-ant-' must be matched before 'sk-').
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ServiceInfo:
    service_id: str
    display_name: str
    docs_url: str


PREFIX_MAP: list[tuple[str, ServiceInfo]] = [
    ("sk-ant-api03-", ServiceInfo("anthropic",       "Anthropic Claude",        "https://console.anthropic.com/keys")),
    ("sk-ant-",       ServiceInfo("anthropic",       "Anthropic Claude",        "https://console.anthropic.com/keys")),
    ("sk-proj-",      ServiceInfo("openai",          "OpenAI (Project)",        "https://platform.openai.com/api-keys")),
    ("sk-svcacct-",   ServiceInfo("openai",          "OpenAI (Service Account)","https://platform.openai.com/api-keys")),
    ("sk-",           ServiceInfo("openai",          "OpenAI",                  "https://platform.openai.com/api-keys")),
    ("gsk_",          ServiceInfo("groq",            "Groq",                    "https://console.groq.com/keys")),
    ("xai-",          ServiceInfo("xai",             "xAI Grok",                "https://console.x.ai")),
    ("AIza",          ServiceInfo("google",          "Google AI / Gemini",      "https://aistudio.google.com/apikey")),
    ("ya29.",         ServiceInfo("google_oauth",    "Google OAuth Token",      "https://developers.google.com")),
    ("pk_live_",      ServiceInfo("stripe_pub",      "Stripe Publishable (Live)","https://dashboard.stripe.com/apikeys")),
    ("sk_live_",      ServiceInfo("stripe_secret",   "Stripe Secret (Live)",    "https://dashboard.stripe.com/apikeys")),
    ("pk_test_",      ServiceInfo("stripe_pub_test", "Stripe Publishable (Test)","https://dashboard.stripe.com/apikeys")),
    ("sk_test_",      ServiceInfo("stripe_sec_test", "Stripe Secret (Test)",    "https://dashboard.stripe.com/apikeys")),
    ("rk_live_",      ServiceInfo("stripe_restricted","Stripe Restricted (Live)","https://dashboard.stripe.com/apikeys")),
    ("github_pat_",   ServiceInfo("github_pat_v2",   "GitHub PAT (Fine-grained)","https://github.com/settings/tokens")),
    ("ghp_",          ServiceInfo("github_pat",      "GitHub PAT (Classic)",    "https://github.com/settings/tokens")),
    ("glpat-",        ServiceInfo("gitlab",          "GitLab PAT",              "https://gitlab.com/-/user_settings/personal_access_tokens")),
    ("SG.",           ServiceInfo("sendgrid",        "SendGrid",                "https://app.sendgrid.com/settings/api_keys")),
    ("AC",            ServiceInfo("twilio",          "Twilio Account SID",      "https://console.twilio.com")),
    ("Bearer ",       ServiceInfo("generic_bearer",  "Generic Bearer Token",    "")),
]


def detect_service(api_key: str) -> Optional[ServiceInfo]:
    """Return the ServiceInfo for the first matching prefix, or None."""
    for prefix, info in PREFIX_MAP:
        if api_key.startswith(prefix):
            return info
    return None


def mask_key(api_key: str, visible_chars: int = 4) -> str:
    """
    Return a masked version for display: sk-...abcd
    Never reveals more than visible_chars characters of the actual key.
    """
    if len(api_key) <= visible_chars + 6:
        return "*" * len(api_key)
    dash_pos = api_key.find("-")
    prefix_end = (dash_pos + 1) if 0 < dash_pos < 10 else 3
    return f"{api_key[:prefix_end]}...{api_key[-visible_chars:]}"
