"""Integración oficial de Publicaciones (Items) de Mercado Libre México."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliItemsClient:
    """Gestión de publicaciones, creación, edición, estado y descripciones."""

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def search_items(
        self,
        user_id: int | str,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        search_type: str | None = None,
    ) -> dict[str, Any]:
        """
        Búsqueda de publicaciones del vendedor.
        Endpoint oficial: GET /users/{user_id}/items/search
        """
        params: dict[str, Any] = {"offset": offset, "limit": min(limit, 50)}
        if status:
            params["status"] = status
        if search_type:
            params["search_type"] = search_type

        return await self._http.get(f"/users/{user_id}/items/search", params=params)

    async def get_item(self, item_id: str) -> dict[str, Any]:
        """
        Consulta detalle completo de una publicación.
        Endpoint oficial: GET /items/{item_id}
        """
        return await self._http.get(f"/items/{item_id}")

    async def get_items_multiget(
        self, item_ids: list[str], attributes: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """
        Consulta por lotes hasta 20 publicaciones en una sola llamada.
        Endpoint oficial: GET /items?ids={id1,id2,...}
        """
        if not item_ids:
            return []

        ids_param = ",".join(item_ids[:20])
        params: dict[str, Any] = {"ids": ids_param}
        if attributes:
            params["attributes"] = ",".join(attributes)

        response = await self._http.get("/items", params=params)
        if isinstance(response, list):
            return [item.get("body", {}) for item in response if item.get("code") == 200]
        return []

    async def create_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Publica un nuevo producto en Mercado Libre México.
        Endpoint oficial: POST /items
        """
        return await self._http.post("/items", json_data=payload)

    async def update_item(self, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Actualiza campos permitidos de una publicación existente.
        Endpoint oficial: PUT /items/{item_id}
        """
        return await self._http.put(f"/items/{item_id}", json_data=payload)

    async def update_item_status(self, item_id: str, status: str) -> dict[str, Any]:
        """
        Cambia el estado de una publicación: 'paused', 'active', 'closed'.
        Endpoint oficial: PUT /items/{item_id}
        """
        return await self._http.put(f"/items/{item_id}", json_data={"status": status})

    async def get_description(self, item_id: str) -> dict[str, Any]:
        """
        Obtiene la descripción en texto plano de una publicación.
        Endpoint oficial: GET /items/{item_id}/description
        """
        return await self._http.get(f"/items/{item_id}/description")

    async def update_description(self, item_id: str, plain_text: str) -> dict[str, Any]:
        """
        Actualiza o crea la descripción de texto plano de una publicación.
        Endpoint oficial: PUT /items/{item_id}/description
        """
        return await self._http.put(f"/items/{item_id}/description", json_data={"plain_text": plain_text})
