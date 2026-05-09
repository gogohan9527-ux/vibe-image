"""Round-trip tests for ``CryptoManager.decrypt_dict``."""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.core.crypto import CryptoManager
from app.errors import CredentialDecryptError


def _encrypt(public_pem: str, plaintext: str) -> str:
    pub = serialization.load_pem_public_key(public_pem.encode("ascii"))
    ct = pub.encrypt(
        plaintext.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ct).decode("ascii")


def test_decrypt_dict_round_trip():
    cm = CryptoManager(key_size=2048)
    pem = cm.public_key_pem()
    payload = {
        "api_key": _encrypt(pem, "sk-test-..."),
        "session_id": _encrypt(pem, "abcd"),
    }
    out = cm.decrypt_dict(payload)
    assert out == {"api_key": "sk-test-...", "session_id": "abcd"}


def test_decrypt_dict_rejects_non_dict():
    cm = CryptoManager(key_size=2048)
    try:
        cm.decrypt_dict("not a dict")  # type: ignore[arg-type]
    except CredentialDecryptError:
        return
    assert False, "expected CredentialDecryptError"


def test_decrypt_dict_rejects_non_string_value():
    cm = CryptoManager(key_size=2048)
    try:
        cm.decrypt_dict({"api_key": 123})  # type: ignore[dict-item]
    except CredentialDecryptError:
        return
    assert False, "expected CredentialDecryptError"
