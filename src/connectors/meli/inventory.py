"""Integración oficial de Inventarios de Mercado Libre México."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliInventoryClient:
    """Sincronización de existencias de publicaciones estándar y consulta de Mercado Envíos Full."""

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def update_stock(self, item_id: str, available_quantity: int) -> dict[str, Any]:
        """
        Actualiza el stock disponible de una publicación simple (no administrada por MeLi FULL).
        Endpoint oficial: PUT /items/{item_id}
        """
        return await self._http.put(
            f"/items/{item_id}", json_data={"available_quantity": max(0, int(available_quantity))}
        )

    async def update_variation_stock(
        self, item_id: str, variation_id: str | int, available_quantity: int
    ) -> dict[str, Any]:
        """
        Actualiza el stock disponible de una variante específica.
        Endpoint oficial: PUT /items/{item_id}/variations/{variation_id}
        """
        return await self._http.put(
            f"/items/{item_id}/variations/{variation_id}",
            json_data={"available_quantity": max(0, int(available_quantity))},
        )

    async def get_fulfillment_stock(
        self, seller_id: int | str, offset: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        """
        Consulta operaciones e inventario custodiado en centros de distribución de Mercado Envíos Full.
        Endpoint oficial: GET /stock/fulfillment/operations/search
        """
        params = {"seller_id": seller_id, "offset": offset, "limit": min(limit, 50)}
        return await self._http.get("/stock/fulfillment/operations/search", params=params)
