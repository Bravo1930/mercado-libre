#!/usr/bin/env python3
"""Script para generar claves de seguridad criptográficas para el archivo .env."""

import secrets
from cryptography.fernet import Fernet

def main():
    jwt_secret = secrets.token_hex(32)
    fernet_key = Fernet.generate_key().decode()
    internal_key = secrets.token_urlsafe(32)

    print("=" * 70)
    print("CLAVES CRIPTOGRÁFICAS GENERADAS PARA EL ARCHIVO .env")
    print("=" * 70)
    print(f"JWT_SECRET_KEY={jwt_secret}")
    print(f"TOKEN_ENCRYPTION_KEY={fernet_key}")
    print(f"INTERNAL_API_KEY={internal_key}")
    print("=" * 70)
    print("Copia y pega estas claves en tu archivo .env antes de producción.")
    print("=" * 70)

if __name__ == "__main__":
    main()
