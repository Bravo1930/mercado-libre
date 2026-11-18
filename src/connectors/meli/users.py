"""Integración de Usuarios y Vendedores de Mercado Libre México."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliUsersClient:
    """Acceso a información oficial de usuario y perfil de vendedor en Mercado Libre."""

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def get_me(self) -> dict[str, Any]:
        """
        Consulta la información completa del vendedor autenticado actual.
        Endpoint oficial: GET /users/me
        """
        return await self._http.get("/users/me")

    async def get_user(self, user_id: int | str) -> dict[str, Any]:
        """
        Consulta información pública de un usuario o comprador en Mercado Libre.
        Endpoint oficial: GET /users/{user_id}
        """
        return await self._http.get(f"/users/{user_id}")
