import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    key = os.getenv("MNEMO_SECRET_KEY", "")
    if not key:
        raise RuntimeError(
            "MNEMO_SECRET_KEY no está configurada (requerida para cifrar credenciales)"
        )
    return Fernet(key.encode("utf-8"))


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_token(enc: str) -> str:
    return _fernet().decrypt(enc.encode("utf-8")).decode("utf-8")
