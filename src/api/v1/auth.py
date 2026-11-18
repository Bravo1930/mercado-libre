"""Módulo de autenticación OAuth 2.0 con Mercado Libre México."""

from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from src.core.config import get_settings
from src.core.logging import get_logger
from src.core.security import encrypt_token

logger = get_logger("auth_meli")
router = APIRouter(prefix="/auth/meli", tags=["Mercado Libre OAuth"])


@router.get("/authorize-url")
def get_meli_authorization_url(company_id: str = Query(..., description="UUID de la empresa vinculante")) -> dict[str, str]:
    """
    Genera el enlace oficial de Mercado Libre México para vincular una cuenta de vendedor.
    Redirige al usuario al portal de autorización de MeLi.
    """
    settings = get_settings()
    params = {
        "response_type": "code",
        "client_id": settings.MELI_APP_ID,
        "redirect_uri": settings.MELI_REDIRECT_URI,
        "state": company_id,  # Permite asociar el callback a la empresa correcta
    }
    url = f"{settings.MELI_AUTH_URL}?{urlencode(params)}"
    return {
        "authorization_url": url,
        "site_id": settings.MELI_SITE_ID,
        "redirect_uri": settings.MELI_REDIRECT_URI,
    }


@router.get("/callback")
async def meli_oauth_callback(
    code: str = Query(..., description="Código temporal de autorización emitido por MeLi"),
    state: str = Query(..., description="Estado / ID de la empresa vinculante"),
) -> dict[str, Any]:
    """
    Callback oficial que recibe el código de autorización y lo canjea por
    el Access Token y el Refresh Token de Mercado Libre.
    """
    settings = get_settings()
    logger.info(f"Procesando callback de autorización para empresa ID='{state}'")

    token_url = f"{settings.MELI_API_BASE_URL}/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.MELI_APP_ID,
        "client_secret": settings.MELI_CLIENT_SECRET,
        "code": code,
        "redirect_uri": settings.MELI_REDIRECT_URI,
    }

    # En entorno de pruebas o desarrollo con credenciales mock:
    if settings.ENVIRONMENT != "production" and settings.MELI_APP_ID == "dev_mock_app_id":
        return {
            "status": "mock_success",
            "message": "Entorno local de desarrollo: flujo OAuth verificado.",
            "company_id": state,
            "mock_user_id": 123456789,
            "expires_in_hours": 6,
        }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(token_url, data=payload)
        if response.status_code != 200:
            logger.error(f"Error al canjear código en Mercado Libre: {response.text}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fallo en la autenticación con la API de Mercado Libre.",
            )
        data = response.json()

    # Encriptación inmediata antes de persistir
    access_token_enc = encrypt_token(data["access_token"])
    refresh_token_enc = encrypt_token(data["refresh_token"])

    return {
        "status": "success",
        "user_id": data["user_id"],
        "token_type": data.get("token_type", "bearer"),
        "expires_in": data["expires_in"],
        "scope": data.get("scope"),
        "encrypted": True,
    }
