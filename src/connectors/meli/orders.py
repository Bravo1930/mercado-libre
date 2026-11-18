"""Integración oficial de Órdenes y Pagos de Mercado Libre México."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliOrdersClient:
    """Búsqueda y consulta de órdenes de venta oficiales de Mercado Libre México."""

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def search_orders(
        self,
        seller_id: int | str,
        order_status: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        offset: int = 0,
        limit: int = 50,
        sort: str = "date_desc",
    ) -> dict[str, Any]:
        """
        Búsqueda de órdenes de venta del vendedor.
        Endpoint oficial: GET /orders/search
        """
        params: dict[str, Any] = {
            "seller": seller_id,
            "offset": offset,
            "limit": min(limit, 50),
            "sort": sort,
        }
        if order_status:
            params["order.status"] = order_status
        if date_from:
            params["order.date_created.from"] = date_from
        if date_to:
            params["order.date_created.to"] = date_to

        return await self._http.get("/orders/search", params=params)

    async def get_order(self, order_id: int | str) -> dict[str, Any]:
        """
        Consulta detalle completo de una orden (partidas, comprador, envíos, pagos).
        Endpoint oficial: GET /orders/{order_id}
        """
        return await self._http.get(f"/orders/{order_id}")

    async def get_payment(self, payment_id: int | str) -> dict[str, Any]:
        """
        Consulta detalle de un cobro/pago procesado por Mercado Pago.
        Endpoint oficial: GET /collections/{payment_id}
        """
        return await self._http.get(f"/collections/{payment_id}")
