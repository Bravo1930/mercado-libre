"""Integración oficial de Finanzas, Liquidaciones y Mercado Pago."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliFinanceClient:
    """
    Submódulo de Finanzas Oficiales de Mercado Libre y Mercado Pago México.
    Permite auditar balances de cuenta, dinero disponible/acreditado,
    liquidaciones bancarias y constancias de retención fiscal SAT.
    """

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def get_user_balance(self, user_id: int | str) -> dict[str, Any]:
        """
        Consulta saldos oficiales en cuenta de Mercado Pago:
        disponible (available_balance), retenido/acreditado (unavailable_balance),
        y total en cuenta.
        Endpoint oficial: GET /users/{user_id}/mercadopago_account/balance
        """
        try:
            return await self._http.get(f"/users/{user_id}/mercadopago_account/balance")
        except Exception:
            # Fallback a endpoint de saldo general de Mercado Pago
            return await self._http.get("/v1/balance")

    async def get_settlements(
        self,
        user_id: int | str,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Consulta liquidaciones periódicas y transferencias bancarias ejecutadas hacia CLABE.
        Endpoint oficial: GET /mercadopago_account/settlements
        """
        params: dict[str, Any] = {"limit": min(limit, 50), "offset": offset}
        if date_from:
            params["begin_date"] = date_from
        if date_to:
            params["end_date"] = date_to

        try:
            return await self._http.get("/mercadopago_account/settlements", params=params)
        except Exception:
            return {"results": [], "paging": {"total": 0, "limit": limit, "offset": offset}}

    async def get_billing_summary(self, user_id: int | str, period: str | None = None) -> dict[str, Any]:
        """
        Consulta el estado de cuenta y facturación de cargos emitida por DeRemate.com de México (MLM).
        Endpoint oficial: GET /billing/integration/monthly_reports
        """
        params: dict[str, Any] = {}
        if period:
            params["period"] = period
        try:
            return await self._http.get("/billing/integration/monthly_reports", params=params)
        except Exception:
            return {"documents": [], "period": period}
