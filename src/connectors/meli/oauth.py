"""Gestor oficial de OAuth 2.0 para Mercado Libre México."""

from typing import Any
import urllib.parse
import httpx

from src.connectors.meli.exceptions import MeliAuthException
from src.core.logging import get_logger

logger = get_logger("meli_oauth")

AUTH_BASE_URL_MX = "https://auth.mercadolibre.com.mx/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


class MeliOAuthManager:
    """Administra el ciclo de vida de credenciales OAuth de Mercado Libre México."""

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        redirect_uri: str,
        auth_url: str = AUTH_BASE_URL_MX,
        token_url: str = TOKEN_URL,
    ):
        self.app_id = app_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.auth_url = auth_url
        self.token_url = token_url

    def get_authorization_url(self, state: str, custom_redirect_uri: str | None = None) -> str:
        """
        Genera la URL oficial de autorización OAuth en Mercado Libre México (auth.mercadolibre.com.mx).
        El parámetro 'state' previene ataques CSRF y contiene el company_id y user_id firmados o encriptados.
        """
        params = {
            "response_type": "code",
            "client_id": self.app_id,
            "redirect_uri": custom_redirect_uri or self.redirect_uri,
            "state": state,
        }
        return f"{self.auth_url}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_token(
        self, code: str, custom_redirect_uri: str | None = None
    ) -> dict[str, Any]:
        """
        Intercambia el authorization code recibido en el callback por access_token y refresh_token.
        Endpoint oficial: POST https://api.mercadolibre.com/oauth/token
        """
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": custom_redirect_uri or self.redirect_uri,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            resp = await client.post(self.token_url, data=payload, headers=headers)
            if not resp.is_success:
                err_data = {}
                try:
                    err_data = resp.json()
                except Exception:
                    pass
                msg = err_data.get("message") or err_data.get("error_description") or resp.text
                err_code = err_data.get("error") or "oauth_exchange_failed"
                logger.error(f"Error al canjear código OAuth en MeLi: {err_code} - {msg}")
                raise MeliAuthException(
                    message=f"Fallo al autenticar con Mercado Libre: {msg}",
                    status_code=resp.status_code,
                    error_code=err_code,
                )

            token_data = resp.json()
            logger.info(
                f"OAuth completado exitosamente para MeLi User ID: {token_data.get('user_id')} "
                f"(Expira en {token_data.get('expires_in')}s)"
            )
            return token_data

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """
        Renueva un token de acceso expirado utilizando el refresh_token.
        MERCADO LIBRE APLICA ROTACIÓN DE REFRESH TOKENS: cada respuesta devuelve un nuevo refresh_token.
        Endpoint oficial: POST https://api.mercadolibre.com/oauth/token
        """
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.app_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            resp = await client.post(self.token_url, data=payload, headers=headers)
            if not resp.is_success:
                err_data = {}
                try:
                    err_data = resp.json()
                except Exception:
                    pass
                msg = err_data.get("message") or err_data.get("error_description") or resp.text
                err_code = err_data.get("error") or "oauth_refresh_failed"
                logger.error(f"Error al refrescar token OAuth en MeLi: {err_code} - {msg}")
                raise MeliAuthException(
                    message=f"No se pudo renovar la sesión de Mercado Libre: {msg}",
                    status_code=resp.status_code,
                    error_code=err_code,
                )

            new_token_data = resp.json()
            logger.info("Access token de Mercado Libre renovado exitosamente.")
            return new_token_data

    async def revoke_app_authorization(self, user_id: int, access_token: str) -> bool:
        """
        Revoca la autorización de la aplicación para el usuario especificado.
        Endpoint oficial: DELETE https://api.mercadolibre.com/users/{user_id}/applications/{app_id}
        """
        url = f"https://api.mercadolibre.com/users/{user_id}/applications/{self.app_id}"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            resp = await client.delete(url, headers=headers)
            if resp.status_code in {200, 204}:
                logger.info(f"Autorización revocada en MeLi para usuario {user_id}")
                return True
            logger.warning(f"Respuesta inesperada al revocar autorización: HTTP {resp.status_code} - {resp.text}")
            return False
