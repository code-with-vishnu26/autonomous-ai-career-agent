"""Encrypted-at-rest browser session persistence (ADR-0020).

The first credentials-adjacent data this project holds: a live, authenticated
Playwright session (cookies + localStorage) that can act *as the user* on a
real site, not merely read a value. That is a categorically higher-stakes
secret than an API key (``core/config.py``'s ``.env`` pattern), so it does
not rest on an assumption about the host's disk configuration -- it is
encrypted at the application level with a key held in the OS keychain
(``keyring``), never written to disk alongside the ciphertext it protects.

**Fail-closed, not fail-open.** If the OS keychain is unavailable (headless
environment, no backend configured), :class:`EncryptedSessionStore` refuses
to persist the session at all -- never a silent fallback to writing it
unencrypted. The cost is a forced manual re-login next run; the alternative
(a plaintext session file that, if it ever leaves the machine via backup,
sync, or a compromised process, is immediately usable by whoever has it) is
not one this project accepts by default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from cryptography.fernet import Fernet, InvalidToken

_KEYRING_SERVICE = "career-agent-browser-session"
_KEYRING_USERNAME = "session-encryption-key"


class SessionEncryptionUnavailableError(Exception):
    """The session's encryption key could not be read or created.

    Raised instead of falling back to unencrypted storage -- callers must
    treat this as "cannot persist this session," never as "persist it
    anyway, unprotected."
    """


class SessionCorruptedError(Exception):
    """A stored session file failed to decrypt with the current key.

    Raised instead of silently discarding it or attempting to use partial
    data -- a session that fails authentication (Fernet is authenticated
    encryption) may have been tampered with or written by a different key;
    either way it must not be trusted.
    """


@runtime_checkable
class KeyProvider(Protocol):
    """Supplies the symmetric key used to encrypt/decrypt session state.

    A narrow port so tests can inject a deterministic, in-memory provider
    instead of touching a real OS keychain -- this environment (and many
    headless/CI environments) has no keyring backend available, so the real
    :class:`KeyringKeyProvider` is disclosed as untestable live in-sandbox,
    the same as every other real external-system client in this project.
    """

    def get_or_create_key(self) -> bytes:
        """Return the persistent symmetric key, creating one on first use."""
        ...


class KeyringKeyProvider:
    """The real :class:`KeyProvider`, backed by the OS credential store."""

    def get_or_create_key(self) -> bytes:
        """Fetch the stored key, or generate and store a new one.

        Raises :class:`SessionEncryptionUnavailableError` if the keyring
        backend cannot be reached -- never generates a key that isn't
        actually persisted in the keychain, which would silently produce a
        session unreadable on the next run.
        """
        import keyring
        import keyring.errors

        try:
            existing = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
        except keyring.errors.KeyringError as exc:
            raise SessionEncryptionUnavailableError(
                f"could not read the session encryption key from the OS "
                f"keychain: {exc}"
            ) from exc
        if existing is not None:
            return existing.encode("utf-8")

        key = Fernet.generate_key()
        try:
            keyring.set_password(
                _KEYRING_SERVICE, _KEYRING_USERNAME, key.decode("utf-8")
            )
        except keyring.errors.KeyringError as exc:
            raise SessionEncryptionUnavailableError(
                f"could not store a new session encryption key in the OS "
                f"keychain: {exc}"
            ) from exc
        return key


class EncryptedSessionStore:
    """Saves/loads a Playwright ``storage_state`` dict, encrypted at rest."""

    def __init__(self, storage_dir: Path, key_provider: KeyProvider) -> None:
        """Configure where sessions live and how the encryption key is obtained."""
        self._dir = storage_dir
        self._key_provider = key_provider
        self._dir.mkdir(parents=True, exist_ok=True)

    def save(self, session_id: str, storage_state: dict[str, object]) -> None:
        """Encrypt and persist ``storage_state`` under ``session_id``.

        Raises :class:`SessionEncryptionUnavailableError` if the key can't
        be obtained -- the session is simply not persisted, never written
        unencrypted as a fallback.
        """
        key = self._key_provider.get_or_create_key()
        fernet = Fernet(key)
        blob = fernet.encrypt(json.dumps(storage_state).encode("utf-8"))
        self._path(session_id).write_bytes(blob)

    def load(self, session_id: str) -> dict[str, object] | None:
        """Decrypt and return the stored session, or ``None`` if none exists.

        Raises :class:`SessionCorruptedError` if the stored bytes fail to
        decrypt with the current key (tampering, or a key mismatch) --
        never returns partial or unverified data.
        """
        path = self._path(session_id)
        if not path.exists():
            return None
        key = self._key_provider.get_or_create_key()
        fernet = Fernet(key)
        try:
            plaintext = fernet.decrypt(path.read_bytes())
        except InvalidToken as exc:
            raise SessionCorruptedError(
                f"session {session_id!r} failed to decrypt -- refusing to "
                f"use it"
            ) from exc
        return json.loads(plaintext)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.session.enc"
