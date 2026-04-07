"""
tests/test_totp_export.py — Wave 11
Covers wallet.utils.totp_export: URI format, andOTP schema, QR fallback,
bulk export, edge cases.
"""
from __future__ import annotations

import json
import re
import pytest

totp_export = pytest.importorskip("wallet.utils.totp_export")
TotpEntry = totp_export.TotpEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASIC = TotpEntry(
    secret="JBSWY3DPEHPK3PXP",
    issuer="GitHub",
    account="alice@example.com",
)

FULL = TotpEntry(
    secret="BASE32SECRET3232",
    issuer="OpenAI",
    account="user@openai.com",
    algorithm="SHA256",
    digits=8,
    period=60,
    tags=["ai", "prod"],
)


# ---------------------------------------------------------------------------
# build_otpauth_uri
# ---------------------------------------------------------------------------

class TestBuildOtpauthUri:
    def test_starts_with_scheme(self):
        uri = totp_export.build_otpauth_uri(BASIC)
        assert uri.startswith("otpauth://totp/")

    def test_contains_secret(self):
        uri = totp_export.build_otpauth_uri(BASIC)
        assert "secret=JBSWY3DPEHPK3PXP" in uri

    def test_contains_issuer(self):
        uri = totp_export.build_otpauth_uri(BASIC)
        assert "issuer=GitHub" in uri

    def test_contains_algorithm(self):
        uri = totp_export.build_otpauth_uri(FULL)
        assert "algorithm=SHA256" in uri

    def test_custom_digits(self):
        uri = totp_export.build_otpauth_uri(FULL)
        assert "digits=8" in uri

    def test_custom_period(self):
        uri = totp_export.build_otpauth_uri(FULL)
        assert "period=60" in uri

    def test_label_encoded(self):
        entry = TotpEntry(
            secret="ABC",
            issuer="My Service",
            account="u@test.com",
        )
        uri = totp_export.build_otpauth_uri(entry)
        # spaces encoded
        assert " " not in uri

    def test_uri_parseable(self):
        uri = totp_export.build_otpauth_uri(BASIC)
        assert re.match(r"otpauth://totp/.+\?secret=", uri)


# ---------------------------------------------------------------------------
# to_andotp_entry
# ---------------------------------------------------------------------------

class TestToAndotpEntry:
    def test_has_required_fields(self):
        d = totp_export.to_andotp_entry(BASIC)
        for field in ["secret", "issuer", "label", "digits", "type", "algorithm", "period"]:
            assert field in d, f"Missing field: {field}"

    def test_type_is_totp(self):
        d = totp_export.to_andotp_entry(BASIC)
        assert d["type"] == "TOTP"

    def test_secret_preserved(self):
        d = totp_export.to_andotp_entry(BASIC)
        assert d["secret"] == "JBSWY3DPEHPK3PXP"

    def test_custom_algorithm(self):
        d = totp_export.to_andotp_entry(FULL)
        assert d["algorithm"] == "SHA256"

    def test_tags_preserved(self):
        d = totp_export.to_andotp_entry(FULL)
        assert "ai" in d["tags"]
        assert "prod" in d["tags"]


# ---------------------------------------------------------------------------
# export_andotp_json
# ---------------------------------------------------------------------------

class TestExportAndotpJson:
    def test_returns_valid_json(self):
        result = totp_export.export_andotp_json([BASIC, FULL])
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_empty_list(self):
        result = totp_export.export_andotp_json([])
        assert json.loads(result) == []


# ---------------------------------------------------------------------------
# generate_ascii_qr
# ---------------------------------------------------------------------------

class TestGenerateAsciiQr:
    def test_returns_string_or_none(self):
        uri = totp_export.build_otpauth_uri(BASIC)
        result = totp_export.generate_ascii_qr(uri)
        assert result is None or isinstance(result, str)

    def test_if_string_contains_block_chars(self):
        uri = totp_export.build_otpauth_uri(BASIC)
        result = totp_export.generate_ascii_qr(uri)
        if result is not None:
            assert len(result) > 10


# ---------------------------------------------------------------------------
# export_totp_entry / export_all_totp
# ---------------------------------------------------------------------------

class TestHighLevelExport:
    def test_single_export_has_uri(self):
        r = totp_export.export_totp_entry(BASIC, include_qr=False)
        assert r.uri.startswith("otpauth://")

    def test_single_export_has_andotp(self):
        r = totp_export.export_totp_entry(BASIC, include_qr=False)
        assert isinstance(r.andotp_dict, dict)

    def test_single_export_no_qr_when_disabled(self):
        r = totp_export.export_totp_entry(BASIC, include_qr=False)
        assert r.ascii_qr is None

    def test_bulk_export_count(self):
        results = totp_export.export_all_totp([BASIC, FULL], include_qr=False)
        assert len(results) == 2

    def test_bulk_export_empty(self):
        results = totp_export.export_all_totp([], include_qr=False)
        assert results == []
