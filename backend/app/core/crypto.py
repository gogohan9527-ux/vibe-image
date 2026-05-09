"""Ephemeral RSA keypair manager for runtime credential transport.

Generates a fresh RSA-2048 keypair on startup; the private key never leaves
process memory and is regenerated whenever the backend restarts. The frontend
fetches the public key (PEM, SubjectPublicKeyInfo), encrypts the user-supplied
api_key with RSA-OAEP(SHA-256), and submits the base64 ciphertext alongside
each task creation request.
"""

from __future__ import annotations

import base64
import threading

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ..errors import CredentialDecryptError


class CryptoManager:
    def __init__(self, key_size: int = 2048) -> None:
        self._lock = threading.Lock()
        self._private_key = rsa.generate_private_key(
            public_exponent=65537, key_size=key_size
        )
        self._public_pem = (
            self._private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("ascii")
        )

    def public_key_pem(self) -> str:
        return self._public_pem

    def decrypt(self, ciphertext_b64: str) -> str:
        try:
            ciphertext = base64.b64decode(ciphertext_b64, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise CredentialDecryptError("encrypted payload is not valid base64") from exc
        with self._lock:
            try:
                plaintext = self._private_key.decrypt(
                    ciphertext,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None,
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - cryptography raises various
                raise CredentialDecryptError(
                    "failed to decrypt credential; the backend may have restarted "
                    "and rotated its keypair — refresh the page and retry"
                ) from exc
        try:
            return plaintext.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CredentialDecryptError("decrypted payload is not valid utf-8") from exc

    def decrypt_dict(self, payload: dict[str, str]) -> dict[str, str]:
        """Decrypt each value (base64 RSA-OAEP ciphertext) into plaintext.

        Used by the providers API to receive multi-field credentials. The
        plaintext dict is intended to be consumed and discarded — callers
        must not log or persist it.
        """
        if not isinstance(payload, dict):
            raise CredentialDecryptError("encrypted_credentials must be an object")
        out: dict[str, str] = {}
        for key, val in payload.items():
            if not isinstance(key, str) or not isinstance(val, str):
                raise CredentialDecryptError(
                    "encrypted_credentials entries must be string -> base64 string"
                )
            out[key] = self.decrypt(val)
        return out
