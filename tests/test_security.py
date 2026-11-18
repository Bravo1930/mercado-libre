"""Pruebas de encriptación simétrica AES y manejo de tokens JWT."""

import pytest
from src.core.security import (
    create_access_token,
    decode_access_token,
    decrypt_token,
    encrypt_token,
    hash_password,
    verify_password,
)


def test_token_encryption_and_decryption():
    """Verifica que el cifrado y descifrado de tokens MeLi sea bidireccional y seguro."""
    original_meli_refresh_token = "TG-672a912e5ab-123456789-mock-refresh-token"
    
    encrypted = encrypt_token(original_meli_refresh_token)
    assert encrypted != original_meli_refresh_token
    assert len(encrypted) > len(original_meli_refresh_token)
    
    decrypted = decrypt_token(encrypted)
    assert decrypted == original_meli_refresh_token


def test_password_hashing():
    """Verifica la generación y validación de contraseñas con bcrypt."""
    password = "SuperSecurePassword123!"
    hashed = hash_password(password)
    
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_generation_and_decoding():
    """Verifica la creación y lectura de JWT de sesión."""
    payload = {"sub": "user_uuid_123", "role": "admin", "tenant_id": "tenant_uuid_456"}
    token = create_access_token(payload)
    
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user_uuid_123"
    assert decoded["tenant_id"] == "tenant_uuid_456"
    assert "exp" in decoded
