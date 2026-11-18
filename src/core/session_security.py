"""Módulo de Control de Sesiones, Detección de Anomalías y Prevención de Robo de Tokens."""

from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.user import UserSession

logger = get_logger("session_security")


class SessionAnomalyDetector:
    """
    Inspecciona en tiempo real las características del cliente conectado contra
    los datos registrados al momento del inicio de sesión (Fingerprint Matching).
    Detecta secuestro de sesión (Session Hijacking) y tokens robados.
    """

    @classmethod
    def evaluate_session_consistency(
        cls,
        session: UserSession,
        current_ip: str | None,
        current_user_agent: str | None,
    ) -> tuple[bool, list[str]]:
        """
        Evalúa si la solicitud actual presenta anomalías severas respecto al origen de la sesión.
        Retorna (is_suspicious, list_of_anomalies).
        """
        anomalies = []

        # 1. Comparación de User-Agent
        if session.user_agent and current_user_agent:
            # Si el navegador o SO cambian radicalmente en una misma sesión activa
            orig_ua = session.user_agent.lower()
            curr_ua = current_user_agent.lower()

            # Detectar cambios entre familias principales (Windows / Mac / Linux / Android / iOS / Postman / curl)
            platforms = ["windows", "macintosh", "linux", "android", "iphone", "postman", "curl", "python"]
            orig_platform = next((p for p in platforms if p in orig_ua), None)
            curr_platform = next((p for p in platforms if p in curr_ua), None)

            if orig_platform and curr_platform and orig_platform != curr_platform:
                anomalies.append(
                    f"Cambio anómalo de plataforma de cliente: de '{orig_platform}' a '{curr_platform}'"
                )

        # 2. Comparación de subred IP
        if session.ip_address and current_ip:
            orig_octets = session.ip_address.split(".")
            curr_octets = current_ip.split(".")
            if len(orig_octets) == 4 and len(curr_octets) == 4:
                # Si los dos primeros octetos cambian (clase B / cambio de ISP radical)
                if orig_octets[:2] != curr_octets[:2] and session.ip_address != "127.0.0.1" and current_ip != "127.0.0.1":
                    anomalies.append(
                        f"Cambio abrupto de subred IP: de '{session.ip_address}' a '{current_ip}'"
                    )

        is_suspicious = len(anomalies) > 0
        if is_suspicious:
            logger.warning(
                f"ALERTA SECUESTRO DE SESIÓN: Sesión JTI='{session.token_jti}' presentó anomalías: {anomalies}"
            )

        return is_suspicious, anomalies


async def revoke_user_sessions(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    except_jti: str | None = None,
) -> int:
    """
    Revoca inmediatamente todas las sesiones activas de un usuario en la base de datos.
    Cualquier petición subsiguiente con los JWTs asociados será rechazada de inmediato.
    """
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.is_revoked == False)
    )
    if except_jti:
        stmt = stmt.where(UserSession.token_jti != except_jti)

    stmt = stmt.values(is_revoked=True)
    res = await db_session.execute(stmt)
    await db_session.flush()
    revoked_count = res.rowcount or 0
    logger.info(f"Revocadas {revoked_count} sesiones activas para el usuario {user_id}")
    return revoked_count
