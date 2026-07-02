"""ADR-0020: encrypted-at-rest browser session storage, fail-closed on an
unavailable OS keychain -- never a silent plaintext fallback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from career_agent.integrations.browser_session import (
    EncryptedSessionStore,
    SessionCorruptedError,
    SessionEncryptionUnavailableError,
)
from tests._fakes import FakeKeyProvider


def test_save_then_load_roundtrips_the_session(tmp_path: Path) -> None:
    store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    state = {"cookies": [{"name": "session", "value": "abc123"}]}
    store.save("greenhouse", state)
    assert store.load("greenhouse") == state


def test_load_returns_none_for_a_session_that_was_never_saved(
    tmp_path: Path,
) -> None:
    store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    assert store.load("never-saved") is None


def test_the_file_on_disk_is_not_plaintext(tmp_path: Path) -> None:
    """The whole point: what's on disk must not be readable without the key."""
    store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    state = {"cookies": [{"name": "session", "value": "super-secret-token"}]}
    store.save("greenhouse", state)
    raw = next(tmp_path.glob("*.session.enc")).read_bytes()
    assert b"super-secret-token" not in raw


def test_save_refuses_to_persist_when_the_keychain_is_unavailable(
    tmp_path: Path,
) -> None:
    """Fail-closed: no key means no session written, encrypted or otherwise --
    never a silent fallback to plaintext."""
    store = EncryptedSessionStore(tmp_path, FakeKeyProvider(unavailable=True))
    with pytest.raises(SessionEncryptionUnavailableError):
        store.save("greenhouse", {"cookies": []})
    assert list(tmp_path.glob("*")) == []


def test_load_refuses_when_the_keychain_is_unavailable(tmp_path: Path) -> None:
    """A previously-saved session can't be read back without the same key
    either -- unavailability blocks both directions, not just writes."""
    working_provider = FakeKeyProvider()
    EncryptedSessionStore(tmp_path, working_provider).save("greenhouse", {"a": 1})
    broken_store = EncryptedSessionStore(tmp_path, FakeKeyProvider(unavailable=True))
    with pytest.raises(SessionEncryptionUnavailableError):
        broken_store.load("greenhouse")


def test_a_tampered_or_wrong_key_session_raises_rather_than_returning_garbage(
    tmp_path: Path,
) -> None:
    EncryptedSessionStore(tmp_path, FakeKeyProvider()).save("greenhouse", {"a": 1})
    different_key_store = EncryptedSessionStore(tmp_path, FakeKeyProvider())
    with pytest.raises(SessionCorruptedError):
        different_key_store.load("greenhouse")
