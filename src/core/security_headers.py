"""Middleware de Encabezados de Seguridad HTTP y Protección contra Ataques Web (OWASP Top 10)."""

from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Inyecta encabezados de seguridad HTTP de nivel bancario en todas las respuestas del ERP.
    Protege contra:
    - Cross-Site Scripting (XSS) y MIME Sniffing.
    - Clickjacking (UI Redressing).
    - Fugas de Referrer y Canales de Comunicación Inseguros (HSTS).
    - Fingerprinting de Servidores y Tecnologías.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)
        settings = get_settings()

        # 1. Content Security Policy (CSP) Estricto
        csp_directives = [
            "default-src 'self'",
            # cdn.tailwindcss.com: Tailwind Play CDN cargado en src/static/index.html:18
            # (tailwind.config se define en línea justo después, línea 20).
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net",
            "font-src 'self' https://fonts.gstatic.com data:",
            "img-src 'self' data: https: blob:",
            # cdn.jsdelivr.net: Chart.js (cdn.jsdelivr.net/npm/chart.js) y su sourcemap .map.
            # fonts.googleapis.com / fonts.gstatic.com: <link rel="preconnect"> de
            # Google Fonts en src/static/index.html (preconnect se rige por connect-src).
            "connect-src 'self' https://api.mercadolibre.com https://cdn.jsdelivr.net https://fonts.googleapis.com https://fonts.gstatic.com",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "object-src 'none'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # 2. Prevención de Clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # 3. Prevención de MIME-Sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 4. Filtro XSS del Navegador
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # 5. Política de Referrer Estricta
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 6. Restricción de Características del Dispositivo (Permissions Policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=(), payment=(), usb=(), display-capture=()"
        )

        # 7. HTTP Strict Transport Security (HSTS) en Entornos Seguros
        if settings.ENVIRONMENT == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        # 8. Eliminar encabezados que revelen versiones de software del servidor
        if "server" in response.headers:
            del response.headers["server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]

        return response
