"""
prefix_detect.py — Auto-detect API key service from known prefixes.

Maintains a registry of known API key prefixes and their metadata.
Used by CLI `add` command to auto-fill the service field.

Known formats:
  - OpenAI: sk-... / sk-proj-... / sk-svcacct-...
  - Anthropic: sk-ant-...
  - Google AI: AIza...
  - GitHub: ghp_... / gho_... / ghs_... / ghr_... / github_pat_...
  - Stripe: sk_live_... / sk_test_... / rk_live_... / rk_test_...
  - AWS: AKIA... / ASIA...
  - SendGrid: SG...
  - Twilio: SK...
  - Hugging Face: hf_...
  - Replicate: r8_...
  - Groq: gsk_...
  - Together AI: togetherai_...
  - Pinecone: (no standard prefix — pcsk_ in newer)
  - Supabase: sbp_...
  - Vercel: vercel_...

Design: prefix matching uses startswith() with longest-prefix-wins.
No regex to keep it fast and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ServiceInfo:
    service_id: str         # machine-readable (e.g., 'openai')
    display_name: str       # human-readable (e.g., 'OpenAI')
    prefix: str             # the matched prefix
    docs_url: str = ""      # optional link to key management page


# Registry: (prefix, ServiceInfo) — order matters for longest-prefix-wins
_REGISTRY: list[tuple[str, ServiceInfo]] = [
    # OpenAI
    ("sk-proj-",      ServiceInfo("openai",    "OpenAI",        "sk-proj-",    "https://platform.openai.com/api-keys")),
    ("sk-svcacct-",   ServiceInfo("openai",    "OpenAI",        "sk-svcacct-", "https://platform.openai.com/api-keys")),
    ("sk-ant-",       ServiceInfo("anthropic", "Anthropic",     "sk-ant-",     "https://console.anthropic.com/settings/keys")),
    ("sk-",           ServiceInfo("openai",    "OpenAI",        "sk-",         "https://platform.openai.com/api-keys")),
    # Google
    ("AIza",          ServiceInfo("google",    "Google AI",     "AIza",        "https://aistudio.google.com/app/apikey")),
    # GitHub
    ("github_pat_",   ServiceInfo("github",    "GitHub",        "github_pat_", "https://github.com/settings/tokens")),
    ("ghp_",          ServiceInfo("github",    "GitHub",        "ghp_",        "https://github.com/settings/tokens")),
    ("gho_",          ServiceInfo("github",    "GitHub",        "gho_")),
    ("ghs_",          ServiceInfo("github",    "GitHub",        "ghs_")),
    ("ghr_",          ServiceInfo("github",    "GitHub",        "ghr_")),
    # Stripe
    ("sk_live_",      ServiceInfo("stripe",    "Stripe",        "sk_live_",    "https://dashboard.stripe.com/apikeys")),
    ("sk_test_",      ServiceInfo("stripe",    "Stripe (Test)", "sk_test_",    "https://dashboard.stripe.com/test/apikeys")),
    ("rk_live_",      ServiceInfo("stripe",    "Stripe",        "rk_live_")),
    ("rk_test_",      ServiceInfo("stripe",    "Stripe (Test)", "rk_test_")),
    # AWS
    ("AKIA",          ServiceInfo("aws",       "AWS",           "AKIA",        "https://console.aws.amazon.com/iam/home")),
    ("ASIA",          ServiceInfo("aws",       "AWS (STS)",     "ASIA")),
    # Groq
    ("gsk_",          ServiceInfo("groq",      "Groq",          "gsk_",        "https://console.groq.com/keys")),
    # Hugging Face
    ("hf_",           ServiceInfo("huggingface", "Hugging Face", "hf_",        "https://huggingface.co/settings/tokens")),
    # Replicate
    ("r8_",           ServiceInfo("replicate", "Replicate",     "r8_",         "https://replicate.com/account/api-tokens")),
    # SendGrid
    ("SG.",           ServiceInfo("sendgrid",  "SendGrid",      "SG.",         "https://app.sendgrid.com/settings/api_keys")),
    # Supabase
    ("sbp_",          ServiceInfo("supabase",  "Supabase",      "sbp_",        "https://supabase.com/dashboard/project/_/settings/api")),
    # Vercel
    ("vercel_",       ServiceInfo("vercel",    "Vercel",        "vercel_",     "https://vercel.com/account/tokens")),
    # Together AI
    ("togetherai_",   ServiceInfo("together",  "Together AI",   "togetherai_")),
    # Twilio
    ("SK",            ServiceInfo("twilio",    "Twilio",        "SK",          "https://console.twilio.com/us1/account/keys")),
]

# Sort by prefix length descending for longest-prefix-wins matching
_REGISTRY.sort(key=lambda x: len(x[0]), reverse=True)


def detect_service(api_key: str) -> Optional[ServiceInfo]:
    """Return ServiceInfo for the first matching prefix, or None."""
    for prefix, info in _REGISTRY:
        if api_key.startswith(prefix):
            return info
    return None


def mask_key(api_key: str, *, visible_chars: int = 8) -> str:
    """
    Return a masked version of the key for safe display.
    Shows up to `visible_chars` characters, then asterisks.

    Examples:
      'sk-prod-abcdefgh...' → 'sk-prod-********'
      'ghp_short'           → 'ghp_****'
    """
    if not api_key:
        return "<empty>"
    shown = api_key[:visible_chars]
    hidden = len(api_key) - visible_chars
    if hidden <= 0:
        return "*" * len(api_key)
    return shown + "*" * min(hidden, 24)


def list_known_services() -> list[ServiceInfo]:
    """Return one ServiceInfo per unique service_id (deduped)."""
    seen: set[str] = set()
    result: list[ServiceInfo] = []
    for _, info in _REGISTRY:
        if info.service_id not in seen:
            seen.add(info.service_id)
            result.append(info)
    return result
