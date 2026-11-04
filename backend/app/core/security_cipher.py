from typing import Optional
from cryptography.fernet import Fernet
from app.core.config import settings


def get_fernet_cipher() -> Fernet:
    key = settings.FERNET_KEY
    if not key or not key.strip():
        raise ValueError("FERNET_KEY no está configurada en las variables de entorno (.env)")
    key_bytes = key.strip().encode("utf-8")
    return Fernet(key_bytes)


def encrypt_api_key(plain_key: str) -> str:
    if not plain_key or not plain_key.strip():
        return ""
    cipher = get_fernet_cipher()
    encrypted_bytes = cipher.encrypt(plain_key.strip().encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_api_key(cipher_text: Optional[str]) -> str:
    if not cipher_text or not cipher_text.strip():
        return ""
    cipher = get_fernet_cipher()
    decrypted_bytes = cipher.decrypt(cipher_text.strip().encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


def mask_api_key(plain_key: str) -> str:
    if not plain_key:
        return ""
    clean = plain_key.strip()
    if len(clean) <= 8:
        return "••••••••"
    return f"{clean[:4]}••••••••{clean[-4:]}"
