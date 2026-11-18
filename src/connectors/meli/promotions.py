"""Integración oficial de Promociones y Campañas de Mercado Libre México."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliPromotionsClient:
    """Consulta de campañas comerciales, promociones y postulación de publicaciones."""

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def get_seller_promotions(
        self, user_id: int | str, promotion_type: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Consulta las promociones disponibles para el vendedor (DEAL, LIGHTNING, etc.).
        Endpoint oficial: GET /seller-promotions/users/{user_id}
        """
        params: dict[str, Any] = {"app_version": "v2"}
        if promotion_type:
            params["promotion_type"] = promotion_type

        res = await self._http.get(f"/seller-promotions/users/{user_id}", params=params)
        return res.get("results", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])

    async def get_promotion(self, promotion_id: str) -> dict[str, Any]:
        """
        Consulta la configuración y plazos de una promoción específica.
        Endpoint oficial: GET /seller-promotions/promotions/{promotion_id}
        """
        return await self._http.get(f"/seller-promotions/promotions/{promotion_id}", params={"app_version": "v2"})

    async def get_promotion_items(
        self, promotion_id: str, status: str = "candidate"
    ) -> list[dict[str, Any]]:
        """
        Consulta las publicaciones candidatas o participantes en una promoción.
        Endpoint oficial: GET /seller-promotions/promotions/{promotion_id}/items
        """
        params = {"status": status, "app_version": "v2"}
        res = await self._http.get(f"/seller-promotions/promotions/{promotion_id}/items", params=params)
        return res.get("results", []) if isinstance(res, dict) else []

    async def optin_promotion_item(
        self, item_id: str, promotion_id: str, promotion_type: str, deal_price: float
    ) -> dict[str, Any]:
        """
        Postula o vincula una publicación a una campaña con precio de oferta.
        Endpoint oficial: POST /seller-promotions/items/{item_id}
        """
        payload = {
            "promotion_id": promotion_id,
            "promotion_type": promotion_type,
            "deal_price": round(float(deal_price), 2),
        }
        return await self._http.post(f"/seller-promotions/items/{item_id}", json_data=payload, params={"app_version": "v2"})
