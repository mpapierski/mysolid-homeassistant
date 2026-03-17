from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def token_key_bytes(access_token: str) -> bytes:
    """Return the AES key format used by the Android app for push payloads."""
    return access_token.replace("-", "").encode("utf-8")


def decrypt_push_message(encoded_message: str, access_token: str) -> bytes:
    """Decrypt the Base64-encoded MySolid push payload."""
    key = token_key_bytes(access_token)
    payload = base64.b64decode(encoded_message)
    encrypted_iv = payload[:16]
    ciphertext = payload[16:]

    ecb_cipher = Cipher(algorithms.AES(key), modes.ECB())
    iv = ecb_cipher.decryptor().update(encrypted_iv) + ecb_cipher.decryptor().finalize()

    cbc_cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    padded = cbc_cipher.decryptor().update(ciphertext) + cbc_cipher.decryptor().finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def decrypt_push_message_json(encoded_message: str, access_token: str) -> dict[str, Any]:
    """Decrypt and JSON-decode a MySolid push payload."""
    return json.loads(decrypt_push_message(encoded_message, access_token).decode("utf-8"))

