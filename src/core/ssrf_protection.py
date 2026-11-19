"""Módulo de Protección contra Server-Side Request Forgery (SSRF) en Peticiones Salientes."""

import ipaddress
import socket
from urllib.parse import urlparse
import httpx

from src.core.exceptions import AppException
from src.core.logging import get_logger

logger = get_logger("ssrf_protection")

# Redes IP Prohibidas para Peticiones Salientes (RFC 1918, RFC 3927, Loopback, Cloud Metadata)
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),          # Loopback IPv4
    ipaddress.ip_network("10.0.0.0/8"),           # Red privada clase A
    ipaddress.ip_network("172.16.0.0/12"),        # Red privada clase B
    ipaddress.ip_network("192.168.0.0/16"),       # Red privada clase C
    ipaddress.ip_network("169.254.0.0/16"),       # Link-Local y Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("0.0.0.0/8"),             # Red actual
    ipaddress.ip_network("224.0.0.0/4"),          # Multicast
    ipaddress.ip_network("240.0.0.0/4"),          # Reservado
    ipaddress.ip_network("255.255.255.255/32"),   # Broadcast
    ipaddress.ip_network("::1/128"),              # Loopback IPv6
    ipaddress.ip_network("fc00::/7"),             # Unique Local IPv6
    ipaddress.ip_network("fe80::/10"),            # Link-Local IPv6
]


class SSRFProtectionException(AppException):
    """Excepción de seguridad lanzada al detectar un intento de SSRF hacia redes no autorizadas."""

    def __init__(self, message: str, url: str | None = None, resolved_ip: str | None = None):
        super().__init__(
            message=message,
            status_code=400,
            code="SSRF_SECURITY_VIOLATION",
            details={"url": url, "resolved_ip": resolved_ip},
        )


def is_ip_allowed(ip_str: str) -> bool:
    """Verifica si una dirección IP pertenece al espacio público enrutible permitido."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    for network in BLOCKED_IP_NETWORKS:
        if ip in network:
            return False

    # Bloqueos adicionales
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
        return False

    return True


def validate_safe_url(
    url: str,
    allowed_domains: list[str] | None = None,
    resolve_dns: bool = True,
) -> str:
    """
    Inspecciona y valida rigurosamente una URL para prevenir ataques SSRF.
    Verifica protocolo, resolución DNS e IPs de destino.

    `resolve_dns=False` omite la resolución DNS en vivo y la inspección de IPs.
    Solo debe usarse para destinos de primera parte fijados por configuración
    del servidor (por ejemplo, el host base oficial de la API de Mercado
    Libre): en ese caso el control aplicable es el esquema + el host, y la
    resolución DNS solo añade fragilidad (proxies, VPN, CGNAT o sandboxes
    donde el host resuelve a rangos no enrutables). Para URLs aportadas por
    usuarios o de origen externo, la resolución DNS debe mantenerse activa.
    """
    if not url or not isinstance(url, str):
        raise SSRFProtectionException("La URL proporcionada es inválida o está vacía.", url=str(url))

    parsed = urlparse(url.strip())

    # 1. Esquema permitido estrictamente http o https
    if parsed.scheme.lower() not in {"http", "https"}:
        raise SSRFProtectionException(
            f"Esquema de protocolo no permitido '{parsed.scheme}'. Solo se autoriza HTTP o HTTPS.",
            url=url,
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFProtectionException("La URL no contiene un nombre de host válido.", url=url)

    # Bloqueo de nombres de host locales directos
    lower_host = hostname.lower()
    if lower_host in {"localhost", "127.0.0.1", "::1", "metadata.google.internal"}:
        raise SSRFProtectionException(
            f"El host de destino '{hostname}' es una dirección local o de metadatos prohibida.",
            url=url,
        )

    # 2. Si se especificó lista blanca de dominios autorizados
    if allowed_domains:
        if not any(lower_host == d.lower() or lower_host.endswith(f".{d.lower()}") for d in allowed_domains):
            raise SSRFProtectionException(
                f"El dominio '{hostname}' no pertenece a la lista blanca autorizada.",
                url=url,
            )

    # 3. Resolución DNS e inspección de direcciones IP (solo cuando aplica:
    #    se omite para destinos de primera parte fijados por configuración)
    if resolve_dns:
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            resolved_ips = {addr[4][0] for addr in addr_info}
        except socket.gaierror as exc:
            raise SSRFProtectionException(f"No fue posible resolver el host '{hostname}': {exc}", url=url)

        for resolved_ip in resolved_ips:
            if not is_ip_allowed(resolved_ip):
                logger.warning(
                    f"ALERTA DE SEGURIDAD SSRF: Intento de conexión bloqueado a {url} "
                    f"que resolvió a la IP prohibida {resolved_ip}"
                )
                raise SSRFProtectionException(
                    f"Acceso denegado por política de ciberseguridad: La dirección IP de destino "
                    f"({resolved_ip}) pertenece a un rango de red interno, privado o de metadatos.",
                    url=url,
                    resolved_ip=resolved_ip,
                )

    return url
