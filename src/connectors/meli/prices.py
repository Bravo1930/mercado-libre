"""Integración oficial de Precios de Mercado Libre México."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliPricesClient:
    """Gestión y actualización de precios en publicaciones simples y con variantes."""

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def update_price(self, item_id: str, new_price: float) -> dict[str, Any]:
        """
        Actualiza el precio de venta de una publicación simple.
        Endpoint oficial: PUT /items/{item_id}
        """
        return await self._http.put(f"/items/{item_id}", json_data={"price": round(float(new_price), 2)})

    async def update_variation_price(
        self, item_id: str, variation_id: str | int, new_price: float
    ) -> dict[str, Any]:
        """
        Actualiza el precio de una variante específica dentro de una publicación.
        Endpoint oficial: PUT /items/{item_id}/variations/{variation_id}
        """
        return await self._http.put(
            f"/items/{item_id}/variations/{variation_id}",
            json_data={"price": round(float(new_price), 2)},
        )

    async def get_prices(self, item_id: str) -> dict[str, Any]:
        """
        Consulta la estructura detallada de precios e historial de un item.
        Endpoint oficial: GET /items/{item_id}/prices
        """
        return await self._http.get(f"/items/{item_id}/prices")
