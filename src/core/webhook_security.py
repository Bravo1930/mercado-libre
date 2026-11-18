"""Módulo de Verificación Criptográfica y Mitigación de Ataques de Repetición en Webhooks."""

from datetime import datetime, timezone
import hashlib
import hmac
import time
from typing import Any

from src.core.config import get_settings
from src.core.exceptions import AppException
from src.core.logging import get_logger

logger = get_logger("webhook_security")

# Ventana máxima permitida para aceptar eventos de webhook (15 minutos = 900 segundos)
MAX_REPLAY_WINDOW_SECONDS = 900


class WebhookSecurityException(AppException):
    """Excepción ante firmas inválidas o detección de repetición de webhooks."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            status_code=401,
            code="WEBHOOK_SECURITY_VIOLATION",
            details=details,
        )


def verify_meli_webhook_signature(
    x_signature_header: str | None,
    raw_body: bytes,
    secret_key: str | None = None,
) -> bool:
    """
    Valida la firma HMAC-SHA256 del webhook de Mercado Libre según el estándar oficial.
    Encabezado esperado: `ts=1672531199,v1=6d2b4f...`
    Neutraliza:
    - Falsificación de eventos por terceros (Spoofing).
    - Manipulación del cuerpo (Tampering).
    - Ataques de repetición temporal (Replay Attacks).
    """
    settings = get_settings()
    secret = secret_key or settings.MELI_CLIENT_SECRET

    # En entornos de desarrollo / testing con secret mock, omitir si no se configuró firma
    if not x_signature_header:
        if settings.ENVIRONMENT in ["development", "testing"] and secret in ["dev_mock_client_secret", ""]:
            return True
        raise WebhookSecurityException("Encabezado de autenticación 'x-signature' no proporcionado.")

    parts = dict(part.split("=", 1) for part in x_signature_header.split(",") if "=" in part)
    ts_str = parts.get("ts")
    v1_sig = parts.get("v1")

    if not ts_str or not v1_sig:
        raise WebhookSecurityException("Estructura de 'x-signature' inválida (ts o v1 faltantes).")

    try:
        ts = int(ts_str)
    except ValueError:
        raise WebhookSecurityException("Timestamp 'ts' inválido en encabezado 'x-signature'.")

    # 1. Verificación de Ventana Temporal (Anti-Replay Attack)
    now_ts = int(time.time())
    age = now_ts - ts

    if age > MAX_REPLAY_WINDOW_SECONDS:
        logger.warning(f"ALERTA REPLAY ATTACK: Webhook expirado rechazado. Antigüedad={age}s > {MAX_REPLAY_WINDOW_SECONDS}s")
        raise WebhookSecurityException(
            f"Evento de webhook expirado (antigüedad de {age}s excede el límite de {MAX_REPLAY_WINDOW_SECONDS}s). Posible ataque de repetición.",
            details={"event_timestamp": ts, "current_timestamp": now_ts, "age_seconds": age},
        )

    if age < -60:  # Fecha futura con margen de 1 minuto por deriva de reloj
        raise WebhookSecurityException("El timestamp del webhook se encuentra en el futuro.")

    # 2. Computar HMAC-SHA256
    # Template estándar: ts + ";" + raw_body
    message = f"id:{ts};{raw_body.decode('utf-8', errors='ignore')}"
    computed_sig = hmac.new(
        key=secret.encode("utf-8"),
        msg=message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    # Comparación de tiempo constante (Anti-Timing Attacks)
    if not hmac.compare_digest(computed_sig, v1_sig):
        # Probar también con raw_body directo para compatibilidad de versiones de API
        alt_sig = hmac.new(
            key=secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(alt_sig, v1_sig):
            logger.warning("Firma criptográfica de webhook no coincide. Rechazando payload no autorizado.")
            raise WebhookSecurityException("Firma HMAC del webhook inválida.")

    return True
