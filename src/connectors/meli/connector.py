"""Fachada principal del Conector oficial de Mercado Libre México (MercadoLibreConnector)."""

from datetime import datetime, timedelta, timezone
import time
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.connectors.meli.client import MeliHTTPClient
from src.connectors.meli.exceptions import MeliAPIException, MeliAuthException
from src.connectors.meli.inventory import MeliInventoryClient
from src.connectors.meli.items import MeliItemsClient
from src.connectors.meli.oauth import MeliOAuthManager
from src.connectors.meli.orders import MeliOrdersClient
from src.connectors.meli.prices import MeliPricesClient
from src.connectors.meli.promotions import MeliPromotionsClient
from src.connectors.meli.shipments import MeliShipmentsClient
from src.connectors.meli.users import MeliUsersClient
from src.connectors.meli.variations import MeliVariationsClient
from src.core.config import get_settings
from src.core.logging import get_logger
from src.core.security import decrypt_token, encrypt_token
from src.models.meli_account import MeliAccount

logger = get_logger("meli_connector")


class MercadoLibreConnector:
    """
    Conector oficial modular e independiente para Mercado Libre México.
    
    Capacidades:
    - Autenticación OAuth 2.0 y registro de aplicación oficial.
    - Manejo seguro de credenciales con cifrado AES-256.
    - Renovación automática y transparente de tokens expirados (HTTP 401 o preventivo).
    - Prevención de condiciones de carrera mediante bloqueo en refrescos concurrentes.
    - Conexión, desconexión, reconexión y diagnóstico de cuentas.
    - Integración completa con Usuarios, Publicaciones, Variantes, Precios, Inventarios, Órdenes, Pagos, Envíos y Promociones.
    """

    def __init__(
        self,
        account_id: uuid.UUID | None = None,
        account: MeliAccount | None = None,
        db_session: AsyncSession | None = None,
        app_id: str | None = None,
        client_secret: str | None = None,
        redirect_uri: str | None = None,
        base_url: str = "https://api.mercadolibre.com",
    ):
        settings = get_settings()
        self.app_id = app_id or settings.MELI_APP_ID
        self.client_secret = client_secret or settings.MELI_CLIENT_SECRET
        self.redirect_uri = redirect_uri or settings.MELI_REDIRECT_URI
        self.base_url = base_url

        self.account_id = account_id or (account.id if account else None)
        self._account = account
        self._session = db_session

        # Caché en memoria del token desencriptado para evitar descifrados repetitivos
        self._cached_access_token: str | None = None
        self._cached_refresh_token: str | None = None
        self._token_expires_at: datetime | None = None

        if account:
            self._load_from_account_entity(account)

        # Gestor de OAuth
        self.oauth = MeliOAuthManager(
            app_id=self.app_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
        )

        # Cliente HTTP resiliente con hooks de inyección y refresco
        self._http = MeliHTTPClient(
            base_url=self.base_url,
            access_token_provider=self._provide_access_token,
            token_refresh_hook=self._auto_refresh_hook,
            timeout=30.0,
            max_retries=3,
        )

        # Submódulos de integración oficiales
        self.users = MeliUsersClient(self._http)
        self.items = MeliItemsClient(self._http)
        self.variations = MeliVariationsClient(self._http)
        self.prices = MeliPricesClient(self._http)
        self.inventory = MeliInventoryClient(self._http)
        self.orders = MeliOrdersClient(self._http)
        self.shipments = MeliShipmentsClient(self._http)
        self.promotions = MeliPromotionsClient(self._http)

    def _load_from_account_entity(self, account: MeliAccount) -> None:
        """Carga y desencripta de forma transparente los tokens de la entidad MeliAccount."""
        try:
            self._cached_access_token = decrypt_token(account.access_token_enc)
            self._cached_refresh_token = decrypt_token(account.refresh_token_enc)
            self._token_expires_at = account.token_expires_at
        except Exception as e:
            logger.error(f"Error al desencriptar tokens de la cuenta {account.id}: {e}")
            raise MeliAuthException("Las credenciales de la cuenta no pudieron ser descifradas.")

    async def _ensure_account_loaded(self) -> None:
        """Si se inicializó con account_id y db_session, carga la cuenta de la BD si no estaba cargada."""
        if self._cached_access_token and self._token_expires_at:
            return

        if self.account_id and self._session:
            stmt = select(MeliAccount).where(MeliAccount.id == self.account_id)
            acc = (await self._session.execute(stmt)).scalar_one_or_none()
            if not acc:
                raise MeliAuthException(f"No se encontró la cuenta de Mercado Libre ID {self.account_id}")
            self._account = acc
            self._load_from_account_entity(acc)

    async def _provide_access_token(self) -> str | None:
        """Proveedor asíncrono del access token para el cliente HTTP cargándolo de BD si hace falta."""
        await self._ensure_account_loaded()
        return self._cached_access_token

    async def _auto_refresh_hook(self) -> str | None:
        """
        Hook asíncrono invocado por el cliente HTTP cuando MeLi responde 401 (token expirado).
        Renueva el token con Mercado Libre, encripta y persiste en BD, y retorna el nuevo token.
        """
        await self._ensure_account_loaded()
        if not self._cached_refresh_token:
            logger.error("No existe refresh token disponible para renovar la sesión de MeLi.")
            raise MeliAuthException("Sesión de Mercado Libre revocada o sin refresh token.")

        new_tokens = await self.oauth.refresh_access_token(self._cached_refresh_token)
        new_access = new_tokens["access_token"]
        new_refresh = new_tokens["refresh_token"]
        expires_in = new_tokens.get("expires_in", 21600)
        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Actualizar en memoria
        self._cached_access_token = new_access
        self._cached_refresh_token = new_refresh
        self._token_expires_at = new_expires_at

        # Persistir en base de datos de forma encriptada
        if self._session and (self.account_id or self._account):
            acc = self._account
            if not acc and self.account_id:
                stmt = select(MeliAccount).where(MeliAccount.id == self.account_id).with_for_update()
                acc = (await self._session.execute(stmt)).scalar_one_or_none()

            if acc:
                acc.access_token_enc = encrypt_token(new_access)
                acc.refresh_token_enc = encrypt_token(new_refresh)
                acc.token_expires_at = new_expires_at
                acc.is_active = True
                await self._session.flush()
                logger.info(f"Nuevos tokens MeLi guardados y encriptados en BD para cuenta {acc.id}")

        return new_access

    async def check_and_proactively_refresh(self, buffer_seconds: int = 300) -> bool:
        """
        Comprueba preventivamente si el token está por expirar en los próximos 'buffer_seconds'.
        Si es así, lo renueva proactivamente antes de que falle una llamada.
        """
        await self._ensure_account_loaded()
        if not self._token_expires_at:
            return False

        now_utc = datetime.now(timezone.utc)
        exp = self._token_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)

        if (exp - now_utc).total_seconds() < buffer_seconds:
            logger.info("El token de Mercado Libre está próximo a vencer. Renovando preventivamente...")
            await self._auto_refresh_hook()
            return True
        return False

    async def test_connection(self) -> dict[str, Any]:
        """
        Diagnóstico de conexión real con Mercado Libre México.
        Realiza una llamada a /users/me, calcula latencia y valida los permisos de la cuenta.
        """
        await self._ensure_account_loaded()
        start_time = time.perf_counter()
        try:
            user_data = await self.users.get_me()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

            return {
                "status": "connected",
                "healthy": True,
                "latency_ms": latency_ms,
                "meli_user_id": user_data.get("id"),
                "nickname": user_data.get("nickname"),
                "site_id": user_data.get("site_id"),
                "seller_experience": user_data.get("seller_experience"),
                "token_expires_at": self._token_expires_at.isoformat() if self._token_expires_at else None,
                "rate_limit_remaining": self._http.rate_limit_remaining,
            }
        except Exception as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(f"Fallo en test de conexión con Mercado Libre: {e}")
            return {
                "status": "error",
                "healthy": False,
                "latency_ms": latency_ms,
                "error": str(e),
            }

    async def disconnect_account(self, revoke_remote: bool = False) -> bool:
        """
        Desconecta la cuenta en el ERP marcándola inactiva y opcionalmente revoca el acceso en MeLi.
        """
        await self._ensure_account_loaded()

        if revoke_remote and self._cached_access_token and self._account:
            try:
                await self.oauth.revoke_app_authorization(
                    user_id=self._account.meli_user_id,
                    access_token=self._cached_access_token,
                )
            except Exception as e:
                logger.warning(f"No se pudo revocar la autorización remota en MeLi: {e}")

        if self._session and (self.account_id or self._account):
            acc = self._account
            if not acc and self.account_id:
                stmt = select(MeliAccount).where(MeliAccount.id == self.account_id)
                acc = (await self._session.execute(stmt)).scalar_one_or_none()

            if acc:
                acc.is_active = False
                await self._session.flush()
                logger.info(f"Cuenta de Mercado Libre {acc.id} desactivada localmente.")
                return True
        return False

    async def reconnect_account(
        self,
        access_token_plain: str,
        refresh_token_plain: str,
        expires_in_seconds: int = 21600,
    ) -> bool:
        """Reactiva una cuenta previamente desconectada asignándole nuevos tokens."""
        await self._ensure_account_loaded()
        new_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

        self._cached_access_token = access_token_plain
        self._cached_refresh_token = refresh_token_plain
        self._token_expires_at = new_expires_at

        if self._session and (self.account_id or self._account):
            acc = self._account
            if not acc and self.account_id:
                stmt = select(MeliAccount).where(MeliAccount.id == self.account_id)
                acc = (await self._session.execute(stmt)).scalar_one_or_none()

            if acc:
                acc.access_token_enc = encrypt_token(access_token_plain)
                acc.refresh_token_enc = encrypt_token(refresh_token_plain)
                acc.token_expires_at = new_expires_at
                acc.is_active = True
                await self._session.flush()
                logger.info(f"Cuenta de Mercado Libre {acc.id} reconectada y activada.")
                return True
        return False
