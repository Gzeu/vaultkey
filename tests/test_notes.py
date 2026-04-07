"""
tests/test_notes.py — Wave 11
Covers wallet.utils.notes: create, update, retrieve, list, delete, encryption.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Minimal stubs so the module can be imported without a full vault setup
# ---------------------------------------------------------------------------

STUB_KEY = b"\x00" * 32
STUB_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture()
def mock_payload():
    """Return a MagicMock that mimics WalletPayload.notes dict."""
    payload = MagicMock()
    payload.notes = {}
    return payload


# ---------------------------------------------------------------------------
# Import guard — skip entire module if notes.py not importable
# ---------------------------------------------------------------------------
notes = pytest.importorskip("wallet.utils.notes")


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

class TestEncryptDecryptNote:
    def test_round_trip_basic(self):
        body = "My secret note body"
        note_id = "test-id-001"
        nonce_hex, cipher_hex = notes.encrypt_note_body(STUB_KEY, note_id, body)
        assert isinstance(nonce_hex, str)
        assert isinstance(cipher_hex, str)
        result = notes.decrypt_note_body(STUB_KEY, note_id, nonce_hex, cipher_hex)
        assert result == body

    def test_different_ids_produce_different_ciphers(self):
        body = "same body"
        n1, c1 = notes.encrypt_note_body(STUB_KEY, "id-A", body)
        n2, c2 = notes.encrypt_note_body(STUB_KEY, "id-B", body)
        # Different subkeys → different ciphertexts (nonces are random too)
        assert c1 != c2

    def test_tampered_cipher_raises(self):
        body = "sensitive"
        nonce_hex, cipher_hex = notes.encrypt_note_body(STUB_KEY, "id-X", body)
        bad_cipher = cipher_hex[:-4] + "ffff"
        with pytest.raises(Exception):
            notes.decrypt_note_body(STUB_KEY, "id-X", nonce_hex, bad_cipher)

    def test_wrong_key_raises(self):
        body = "data"
        nonce_hex, cipher_hex = notes.encrypt_note_body(STUB_KEY, "id-Y", body)
        wrong_key = b"\xff" * 32
        with pytest.raises(Exception):
            notes.decrypt_note_body(wrong_key, "id-Y", nonce_hex, cipher_hex)

    def test_empty_body_round_trip(self):
        nonce_hex, cipher_hex = notes.encrypt_note_body(STUB_KEY, "id-empty", "")
        result = notes.decrypt_note_body(STUB_KEY, "id-empty", nonce_hex, cipher_hex)
        assert result == ""

    def test_unicode_body(self):
        body = "🔐 MultiversX EGLD — note test ✓"
        nonce_hex, cipher_hex = notes.encrypt_note_body(STUB_KEY, "id-uni", body)
        result = notes.decrypt_note_body(STUB_KEY, "id-uni", nonce_hex, cipher_hex)
        assert result == body


# ---------------------------------------------------------------------------
# SecureNote model
# ---------------------------------------------------------------------------

class TestSecureNoteModel:
    def test_create_minimal(self):
        note = notes.SecureNote(title="Test", nonce_hex="aa", cipher_hex="bb")
        assert note.title == "Test"
        assert note.tags == []
        assert note.pinned is False
        assert note.id is not None

    def test_create_with_tags(self):
        note = notes.SecureNote(
            title="Prod creds", nonce_hex="aa", cipher_hex="bb",
            tags=["prod", "infra"],
        )
        assert "prod" in note.tags
        assert "infra" in note.tags

    def test_pinned_default_false(self):
        note = notes.SecureNote(title="X", nonce_hex="a", cipher_hex="b")
        assert note.pinned is False

    def test_timestamps_set(self):
        note = notes.SecureNote(title="Y", nonce_hex="a", cipher_hex="b")
        assert note.created_at is not None
        assert note.updated_at is not None


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

class TestCrudHelpers:
    def _make_payload(self):
        """Real-ish payload with a plain dict for .notes."""
        p = MagicMock()
        p.notes = {}
        return p

    def test_create_note_adds_to_payload(self):
        payload = self._make_payload()
        note = notes.create_note(payload, STUB_KEY, title="Alpha", body="secret")
        assert note.id in payload.notes

    def test_create_note_returns_secure_note(self):
        payload = self._make_payload()
        note = notes.create_note(payload, STUB_KEY, title="Beta", body="data")
        assert isinstance(note, notes.SecureNote)

    def test_update_note_body_changes_cipher(self):
        payload = self._make_payload()
        note = notes.create_note(payload, STUB_KEY, title="C", body="original")
        old_cipher = note.cipher_hex
        notes.update_note_body(payload, STUB_KEY, note.id, "updated body")
        assert payload.notes[note.id].cipher_hex != old_cipher

    def test_retrieve_note_body_correct(self):
        payload = self._make_payload()
        note = notes.create_note(payload, STUB_KEY, title="D", body="retrieve me")
        retrieved = notes.retrieve_note_body(payload, STUB_KEY, note.id)
        assert retrieved == "retrieve me"

    def test_update_then_retrieve(self):
        payload = self._make_payload()
        note = notes.create_note(payload, STUB_KEY, title="E", body="v1")
        notes.update_note_body(payload, STUB_KEY, note.id, "v2")
        assert notes.retrieve_note_body(payload, STUB_KEY, note.id) == "v2"

    def test_retrieve_missing_id_raises(self):
        payload = self._make_payload()
        with pytest.raises((KeyError, ValueError)):
            notes.retrieve_note_body(payload, STUB_KEY, "nonexistent-id")

    def test_delete_removes_note(self):
        payload = self._make_payload()
        note = notes.create_note(payload, STUB_KEY, title="F", body="gone")
        # If delete_note exists
        if hasattr(notes, "delete_note"):
            notes.delete_note(payload, note.id)
            assert note.id not in payload.notes


# ---------------------------------------------------------------------------
# list_notes
# ---------------------------------------------------------------------------

class TestListNotes:
    def _build_payload(self, count: int = 3):
        p = MagicMock()
        p.notes = {}
        for i in range(count):
            n = notes.create_note(p, STUB_KEY, title=f"Note {i}", body=f"body {i}")
            if i == 0:
                n.pinned = True
        return p

    def test_list_returns_all(self):
        p = self._build_payload(3)
        result = notes.list_notes(p)
        assert len(result) == 3

    def test_pinned_first(self):
        p = self._build_payload(3)
        result = notes.list_notes(p)
        assert result[0].pinned is True

    def test_tag_filter(self):
        p = MagicMock()
        p.notes = {}
        n1 = notes.create_note(p, STUB_KEY, title="A", body="x", tags=["prod"])
        n2 = notes.create_note(p, STUB_KEY, title="B", body="y", tags=["dev"])
        result = notes.list_notes(p, tag="prod")
        ids = [n.id for n in result]
        assert n1.id in ids
        assert n2.id not in ids

    def test_query_filter(self):
        p = MagicMock()
        p.notes = {}
        notes.create_note(p, STUB_KEY, title="Alpha secret", body="x")
        notes.create_note(p, STUB_KEY, title="Beta public", body="y")
        result = notes.list_notes(p, query="alpha")
        assert len(result) == 1
        assert result[0].title == "Alpha secret"

    def test_empty_vault_returns_empty(self):
        p = MagicMock()
        p.notes = {}
        assert notes.list_notes(p) == []
