from __future__ import annotations

import base64

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.mysolid.crypto import decrypt_push_message, token_key_bytes
from custom_components.mysolid.push import _generate_fid


def _encrypt_for_test(plaintext: bytes, access_token: str) -> str:
    key = token_key_bytes(access_token)
    iv = bytes(range(16))
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cbc_cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    ciphertext = cbc_cipher.encryptor().update(padded) + cbc_cipher.encryptor().finalize()
    ecb_cipher = Cipher(algorithms.AES(key), modes.ECB())
    encrypted_iv = ecb_cipher.encryptor().update(iv) + ecb_cipher.encryptor().finalize()
    return base64.b64encode(encrypted_iv + ciphertext).decode("ascii")


def test_decrypt_push_message_roundtrip() -> None:
    access_token = "12345678-1234-1234-1234-123456789abc"
    encoded = _encrypt_for_test(b'{"armed":true}', access_token)
    assert decrypt_push_message(encoded, access_token) == b'{"armed":true}'


def test_generate_fid_shape() -> None:
    fid = _generate_fid()
    assert len(fid) == 22
    assert "=" not in fid
