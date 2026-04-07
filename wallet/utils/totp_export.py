"""
totp_export.py — Wave 11
Export TOTP secrets from VaultKey in industry-standard formats:
  • otpauth:// URI (RFC 6238 / Google Authenticator)
  • andOTP JSON backup format
  • ASCII QR code (requires qrcode[pil] opt-dep; graceful fallback)

No secrets are written to disk by this module — callers decide persistence.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import List, Optional
from urllib.parse import quote


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TotpEntry:
    """Minimal TOTP parameters needed for export."""
    secret: str            # base32-encoded TOTP secret
    issuer: str            # e.g. "GitHub", "OpenAI"
    account: str           # e.g. "user@example.com"
    algorithm: str = "SHA1"
    digits: int = 6
    period: int = 30
    thumbnail: str = "Default"
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# otpauth URI builder
# ---------------------------------------------------------------------------

def build_otpauth_uri(
    entry: TotpEntry,
    *,
    otp_type: str = "totp",
) -> str:
    """
    Build a standard otpauth:// URI.

    Format:  otpauth://totp/ISSUER:ACCOUNT?secret=...&issuer=...&algorithm=...&digits=...&period=...

    >>> uri = build_otpauth_uri(TotpEntry(secret="JBSWY3DPEHPK3PXP", issuer="Example", account="user@example.com"))
    >>> uri.startswith("otpauth://totp/")
    True
    """
    label = quote(f"{entry.issuer}:{entry.account}", safe="")
    params = (
        f"secret={entry.secret}"
        f"&issuer={quote(entry.issuer, safe='')}"
        f"&algorithm={entry.algorithm}"
        f"&digits={entry.digits}"
        f"&period={entry.period}"
    )
    return f"otpauth://{otp_type}/{label}?{params}"


# ---------------------------------------------------------------------------
# andOTP JSON export
# ---------------------------------------------------------------------------

def to_andotp_entry(entry: TotpEntry) -> dict:
    """
    Convert a TotpEntry to the andOTP JSON format (v0.8+).

    andOTP format reference:
      https://github.com/andOTP/andOTP/wiki/Backup-format
    """
    return {
        "secret": entry.secret,
        "issuer": entry.issuer,
        "label": f"{entry.issuer}:{entry.account}",
        "digits": entry.digits,
        "type": "TOTP",
        "algorithm": entry.algorithm,
        "thumbnail": entry.thumbnail,
        "last_used": int(time.time() * 1000),
        "used_frequency": 0,
        "period": entry.period,
        "tags": entry.tags,
    }


def export_andotp_json(entries: list[TotpEntry]) -> str:
    """
    Serialise a list of TotpEntry objects to an andOTP-compatible JSON string.

    The result can be saved as ``vaultkey_totp_backup.json`` and imported
    directly into andOTP, Aegis (via andOTP import), or Raivo OTP.

    :param entries: list of TotpEntry
    :returns: JSON string
    """
    return json.dumps([to_andotp_entry(e) for e in entries], indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# ASCII QR code (optional qrcode dep)
# ---------------------------------------------------------------------------

def generate_ascii_qr(uri: str) -> Optional[str]:
    """
    Generate an ASCII-art QR code for a given otpauth URI.

    Requires ``qrcode`` package (``pip install qrcode[pil]``).
    Returns None gracefully if the package is not installed.
    """
    try:
        import qrcode  # type: ignore
        import io
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        buf = io.StringIO()
        qr.print_ascii(out=buf)
        return buf.getvalue()
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# High-level helper
# ---------------------------------------------------------------------------

@dataclass
class TotpExportResult:
    entry: TotpEntry
    uri: str
    andotp_dict: dict
    ascii_qr: Optional[str] = None


def export_totp_entry(
    entry: TotpEntry,
    *,
    include_qr: bool = True,
) -> TotpExportResult:
    """
    Export a single TotpEntry to all supported formats.

    :param entry:       The TotpEntry to export.
    :param include_qr:  Whether to attempt ASCII QR generation.
    :returns:           TotpExportResult with uri, andotp_dict, ascii_qr.
    """
    uri = build_otpauth_uri(entry)
    andotp = to_andotp_entry(entry)
    qr = generate_ascii_qr(uri) if include_qr else None
    return TotpExportResult(entry=entry, uri=uri, andotp_dict=andotp, ascii_qr=qr)


def export_all_totp(entries: list[TotpEntry], *, include_qr: bool = False) -> list[TotpExportResult]:
    """
    Bulk-export a list of TOTP entries.

    :param entries:    List of TotpEntry.
    :param include_qr: Generate QR codes (slow for large lists).
    :returns:          List of TotpExportResult.
    """
    return [export_totp_entry(e, include_qr=include_qr) for e in entries]
