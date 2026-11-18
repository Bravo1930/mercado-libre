"""Módulo de seguridad, encriptación de credenciales MeLi y manejo de sesiones."""

from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger("security")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_fernet_cipher() -> Fernet:
    """Obtiene la instancia de cifrado simétrico AES con la clave del entorno."""
    settings = get_settings()
    key = settings.TOKEN_ENCRYPTION_KEY
    if not key or len(key) < 32:
        raise ValueError("TOKEN_ENCRYPTION_KEY no está configurada o es inválida.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plain_token: str) -> str:
    """Encripta un token de Mercado Libre (Access o Refresh) antes de guardarlo en BD."""
    if not plain_token:
        return ""
    cipher = get_fernet_cipher()
    encrypted_bytes = cipher.encrypt(plain_token.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """Desencripta un token de Mercado Libre para su uso en llamadas a la API oficial."""
    if not encrypted_token:
        return ""
    cipher = get_fernet_cipher()
    try:
        decrypted_bytes = cipher.decrypt(encrypted_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        logger.error("Fallo al desencriptar el token de Mercado Libre. Clave corrupta o modificada.")
        raise ValueError("Token encriptado inválido o corrupto.")


def hash_password(password: str) -> str:
    """Genera el hash seguro de una contraseña."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica si la contraseña en texto plano coincide con el hash almacenado."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Genera un JWT de sesión firmado para usuarios del ERP."""
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decodifica y valida un JWT de sesión."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as exc:
        logger.warning(f"Intento de autenticación con JWT inválido: {exc}")
        return None
