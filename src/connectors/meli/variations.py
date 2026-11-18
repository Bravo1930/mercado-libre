"""Integración oficial de Variantes de Publicaciones en Mercado Libre México."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliVariationsClient:
    """Gestión de variantes de publicaciones (colores, tallas, capacidades)."""

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def get_variations(self, item_id: str) -> list[dict[str, Any]]:
        """
        Consulta todas las variaciones asociadas a un item.
        Endpoint oficial: GET /items/{item_id}/variations
        """
        res = await self._http.get(f"/items/{item_id}/variations")
        return res if isinstance(res, list) else []

    async def get_variation(self, item_id: str, variation_id: str | int) -> dict[str, Any]:
        """
        Consulta detalle de una variación específica.
        Endpoint oficial: GET /items/{item_id}/variations/{variation_id}
        """
        return await self._http.get(f"/items/{item_id}/variations/{variation_id}")

    async def add_variation(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Agrega una nueva variación a un item existente.
        Endpoint oficial: POST /items/{item_id}/variations
        """
        return await self._http.post(f"/items/{item_id}/variations", json_data=payload)

    async def update_variation(
        self, item_id: str, variation_id: str | int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Actualiza los datos de una variación específica (precio, stock, combinaciones).
        Endpoint oficial: PUT /items/{item_id}/variations/{variation_id}
        """
        return await self._http.put(f"/items/{item_id}/variations/{variation_id}", json_data=payload)

    async def delete_variation(self, item_id: str, variation_id: str | int) -> dict[str, Any]:
        """
        Elimina una variación de la publicación.
        Endpoint oficial: DELETE /items/{item_id}/variations/{variation_id}
        """
        return await self._http.delete(f"/items/{item_id}/variations/{variation_id}")
