"""Integración oficial de Envíos y Etiquetas (Mercado Envíos) de Mercado Libre México."""

from typing import Any
from src.connectors.meli.client import MeliHTTPClient


class MeliShipmentsClient:
    """Consulta de estados de envío, rastreo y descarga de guías/etiquetas oficiales."""

    def __init__(self, http_client: MeliHTTPClient):
        self._http = http_client

    async def get_shipment(self, shipment_id: int | str) -> dict[str, Any]:
        """
        Consulta detalle completo de un envío (estatus, subestatus, tracking, método logístico).
        Endpoint oficial: GET /shipments/{shipment_id}
        """
        return await self._http.get(f"/shipments/{shipment_id}")

    async def get_shipment_labels(
        self, shipment_ids: list[int | str], response_type: str = "pdf"
    ) -> bytes:
        """
        Descarga oficial de etiquetas de envío en formato PDF o ZPL2.
        Endpoint oficial: GET /shipment_labels?shipment_ids={ids}&response_type={response_type}
        """
        if not shipment_ids:
            return b""

        ids_param = ",".join(str(sid) for sid in shipment_ids[:50])
        params = {
            "shipment_ids": ids_param,
            "response_type": response_type,  # 'pdf' o 'zpl2'
        }
        return await self._http.download_bytes("/shipment_labels", params=params)
