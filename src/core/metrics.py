"""Sistema de métricas del ERP compatible con Prometheus / OpenMetrics.

Permite recopilar y exponer métricas de rendimiento HTTP, estado de base de datos,
eventos de negocio, alertas de seguridad y métricas SaaS sin dependencias binarias externas.
"""

import time
from typing import Dict, Tuple
from collections import defaultdict
from fastapi import Request, Response
from src.core.logging import get_logger

logger = get_logger("metrics")

class MetricsRegistry:
    """Registro en memoria de métricas operativas con formato de exportación Prometheus."""

    def __init__(self):
        # HTTP Counters: (method, path, status_code) -> count
        self.http_requests_total: Dict[Tuple[str, str, int], int] = defaultdict(int)
        
        # HTTP Duration: (method, path) -> (count, total_seconds)
        self.http_request_duration_seconds: Dict[Tuple[str, str], Tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        
        # Business Counters
        self.business_events_total: Dict[str, int] = defaultdict(int)
        
        # Gauges
        self.system_gauges: Dict[str, float] = {
            "erp_database_connected": 1.0,
            "erp_redis_connected": 1.0,
            "erp_saas_active_companies": 0.0,
            "erp_security_active_alerts": 0.0,
        }

    def record_http_request(self, method: str, path: str, status_code: int, duration_seconds: float):
        """Registra una petición HTTP procesada."""
        # Sanitizar path para evitar cardinalidad explosiva con IDs dinámicos
        sanitized_path = self._sanitize_path(path)
        self.http_requests_total[(method, sanitized_path, status_code)] += 1
        
        count, total_dur = self.http_request_duration_seconds[(method, sanitized_path)]
        self.http_request_duration_seconds[(method, sanitized_path)] = (count + 1, total_dur + duration_seconds)

    def record_business_event(self, event_name: str, count: int = 1):
        """Incrementa el contador de un evento de negocio (ej. 'order_created', 'webhook_processed')."""
        self.business_events_total[event_name] += count

    def set_gauge(self, gauge_name: str, value: float):
        """Establece el valor instantáneo de un gauge."""
        self.system_gauges[gauge_name] = float(value)

    def _sanitize_path(self, path: str) -> str:
        """Agrupa URLs con UUIDs o IDs numéricos en patrones para evitar alta cardinalidad."""
        import re
        # Reemplazar UUIDs
        path = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "{id}", path)
        # Reemplazar IDs numéricos largos
        path = re.sub(r"/\d+(?=/|$)", "/{id}", path)
        return path

    def generate_prometheus_text(self) -> str:
        """Genera el texto de métricas en formato estándar de Prometheus (text/plain)."""
        lines = []
        lines.append("# HELP erp_http_requests_total Total de solicitudes HTTP procesadas")
        lines.append("# TYPE erp_http_requests_total counter")
        for (method, path, status_code), count in sorted(self.http_requests_total.items()):
            lines.append(f'erp_http_requests_total{{method="{method}",path="{path}",status="{status_code}"}} {count}')

        lines.append("")
        lines.append("# HELP erp_http_request_duration_seconds_sum Tiempo acumulado de duracion de solicitudes HTTP en segundos")
        lines.append("# TYPE erp_http_request_duration_seconds_sum counter")
        for (method, path), (count, total_dur) in sorted(self.http_request_duration_seconds.items()):
            lines.append(f'erp_http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {round(total_dur, 4)}')
            lines.append(f'erp_http_request_duration_seconds_count{{method="{method}",path="{path}"}} {count}')

        lines.append("")
        lines.append("# HELP erp_business_events_total Conteo de eventos operacionales y transaccionales del ERP")
        lines.append("# TYPE erp_business_events_total counter")
        for event, count in sorted(self.business_events_total.items()):
            lines.append(f'erp_business_events_total{{event="{event}"}} {count}')

        lines.append("")
        lines.append("# HELP erp_system_status Indicadores instantáneos del sistema")
        lines.append("# TYPE erp_system_status gauge")
        for gauge, val in sorted(self.system_gauges.items()):
            lines.append(f'{gauge} {val}')

        lines.append("")
        return "\n".join(lines)


# Instancia singleton de métricas
metrics_registry = MetricsRegistry()


async def metrics_endpoint(request: Request) -> Response:
    """Endpoint HTTP /metrics para recolección por Prometheus."""
    content = metrics_registry.generate_prometheus_text()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
