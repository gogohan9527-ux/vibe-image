"""AES-256-GCM at-rest encryption for provider credentials.

Master key resolution (in order of precedence):

1. ``VIBE_SECRET_KEY`` env var. Accepts hex (64 chars) or base64 (44 chars).
2. ``data/master.key`` file (32 raw bytes).
3. Auto-generate 32 bytes via ``os.urandom`` and persist to
   ``data/master.key`` with permission ``0o600`` on POSIX. (Windows: chmod is
   silently skipped — see README.)

Ciphertext layout: ``nonce(12) || ciphertext || tag(16)``.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_KEY_BYTES = 32
_NONCE_BYTES = 12


class SecretBoxError(RuntimeError):
    """Raised on master-key resolution failures or decryption failures."""


def _resolve_master_key(
    env: dict | None = None, key_file: Path | None = None
) -> bytes:
    env = env if env is not None else os.environ
    raw_env = env.get("VIBE_SECRET_KEY")
    if raw_env:
        return _decode_env_secret(raw_env)
    if key_file is None:
        return os.urandom(_KEY_BYTES)
    if key_file.exists():
        data = key_file.read_bytes()
        if len(data) != _KEY_BYTES:
            raise SecretBoxError(
                f"master key file {key_file} is {len(data)} bytes, expected {_KEY_BYTES}"
            )
        return data
    # Auto-generate.
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(_KEY_BYTES)
    key_file.write_bytes(key)
    try:
        os.chmod(key_file, 0o600)
    except (OSError, NotImplementedError):
        # Windows: chmod is best-effort; documented in README.
        pass
    return key


def _decode_env_secret(raw: str) -> bytes:
    raw = raw.strip()
    # Try hex first.
    if len(raw) == _KEY_BYTES * 2:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    # Then base64 (44 chars when standard / 43 chars unpadded for 32 bytes).
    try:
        decoded = base64.b64decode(raw, validate=True)
        if len(decoded) == _KEY_BYTES:
            return decoded
    except (ValueError, base64.binascii.Error):
        pass
    raise SecretBoxError(
        "VIBE_SECRET_KEY must be 32 bytes encoded as hex (64 chars) or base64 (44 chars)"
    )


class SecretBox:
    """AES-256-GCM helper bound to a master key resolved at construction."""

    def __init__(
        self, key_file: Path | None = None, env: dict | None = None
    ) -> None:
        self._key = _resolve_master_key(env=env, key_file=key_file)
        self._aead = AESGCM(self._key)

    def encrypt(self, plaintext: bytes) -> bytes:
        if not isinstance(plaintext, (bytes, bytearray)):
            raise TypeError("encrypt() requires bytes")
        nonce = os.urandom(_NONCE_BYTES)
        ct = self._aead.encrypt(nonce, bytes(plaintext), associated_data=None)
        return nonce + ct

    def decrypt(self, blob: bytes) -> bytes:
        if not isinstance(blob, (bytes, bytearray)):
            raise TypeError("decrypt() requires bytes")
        if len(blob) < _NONCE_BYTES + 16:
            raise SecretBoxError("ciphertext too short")
        nonce = bytes(blob[:_NONCE_BYTES])
        body = bytes(blob[_NONCE_BYTES:])
        try:
            return self._aead.decrypt(nonce, body, associated_data=None)
        except Exception as exc:  # noqa: BLE001 - cryptography raises various
            raise SecretBoxError("decryption failed") from exc
