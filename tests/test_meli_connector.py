"""Pruebas exhaustivas para el módulo independiente MercadoLibreConnector y endpoints REST."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import uuid
import httpx
import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.connectors.meli import (
    MercadoLibreConnector,
    MeliAPIException,
    MeliAuthException,
    MeliRateLimitException,
    MeliTokenExpiredException,
)
from src.core.database import get_db
from src.core.security import decrypt_token, encrypt_token
from src.main import app
from src.models import Base
from src.models.meli_account import MeliAccount


@pytest.fixture
def meli_test_context(tmp_path):
    """Provee un cliente HTTP, contexto multi-empresa y base de datos aislada para pruebas."""
    db_file = tmp_path / "meli_connector_test.db"
    sync_engine = sa.create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    session_factory = async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        unique_id = uuid.uuid4().hex[:6]
        # 1. Registrar Tenant y Empresa
        reg_res = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant MeLi {unique_id}",
            "tenant_slug": f"meli-slug-{unique_id}",
            "company_legal_name": f"Empresa Conector S.A. {unique_id}",
            "company_rfc": "MEL991201AB0",
            "admin_email": f"admin_meli_{unique_id}@test.com",
            "admin_password": "PasswordMeli1!",
            "admin_full_name": "Admin MeLi Connector",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        # 2. Iniciar sesión para obtener JWT
        login_res = client.post("/api/v1/auth/login", json={
            "email": f"admin_meli_{unique_id}@test.com",
            "password": "PasswordMeli1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        yield {
            "client": client,
            "headers": headers,
            "company_id": company_id,
            "session_factory": session_factory,
        }

    app.dependency_overrides.clear()


# ==============================================================================
# 1. PRUEBAS DE OAUTH 2.0 Y RESILIENCIA
# ==============================================================================


def test_oauth_authorization_url_generation():
    """Verifica que la URL generada apunte al endpoint oficial de México y contenga parámetros obligatorios."""
    connector = MercadoLibreConnector(
        app_id="1234567890",
        client_secret="secret_abc",
        redirect_uri="https://mi-erp.com/callback",
    )
    auth_url = connector.oauth.get_authorization_url(state="secure_state_123")

    assert "https://auth.mercadolibre.com.mx/authorization" in auth_url
    assert "response_type=code" in auth_url
    assert "client_id=1234567890" in auth_url
    assert "redirect_uri=https%3A%2F%2Fmi-erp.com%2Fcallback" in auth_url
    assert "state=secure_state_123" in auth_url


@pytest.mark.asyncio
async def test_oauth_code_exchange_success():
    """Prueba el intercambio del código de autorización por tokens de acceso oficiales."""
    connector = MercadoLibreConnector(
        app_id="1234567890",
        client_secret="secret_abc",
        redirect_uri="https://mi-erp.com/callback",
    )

    mock_token_response = {
        "access_token": "APP_USR-123456-token",
        "token_type": "bearer",
        "expires_in": 21600,
        "scope": "offline_access read write",
        "user_id": 99887766,
        "refresh_token": "TG-67890-refresh",
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = httpx.Response(
            200,
            json=mock_token_response,
            request=httpx.Request("POST", "https://api.mercadolibre.com/oauth/token"),
        )

        tokens = await connector.oauth.exchange_code_for_token("TG-auth-code-123")
        assert tokens["access_token"] == "APP_USR-123456-token"
        assert tokens["refresh_token"] == "TG-67890-refresh"
        assert tokens["user_id"] == 99887766


@pytest.mark.asyncio
async def test_oauth_refresh_access_token():
    """Prueba la renovación de access token mediante refresh token."""
    connector = MercadoLibreConnector(
        app_id="1234567890",
        client_secret="secret_abc",
        redirect_uri="https://mi-erp.com/callback",
    )

    mock_refresh_response = {
        "access_token": "APP_USR-NEW-access",
        "token_type": "bearer",
        "expires_in": 21600,
        "refresh_token": "TG-NEW-refresh",
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = httpx.Response(
            200,
            json=mock_refresh_response,
            request=httpx.Request("POST", "https://api.mercadolibre.com/oauth/token"),
        )

        new_tokens = await connector.oauth.refresh_access_token("TG-OLD-refresh")
        assert new_tokens["access_token"] == "APP_USR-NEW-access"
        assert new_tokens["refresh_token"] == "TG-NEW-refresh"


@pytest.mark.asyncio
async def test_auto_token_refresh_on_401_expired(meli_test_context):
    """
    PRUEBA CRÍTICA DE RESILIENCIA:
    Simula una respuesta HTTP 401 con 'expired_token'.
    El conector debe renovar automáticamente el token con MeLi, actualizar la BD y reintentar con éxito.
    """
    session_factory = meli_test_context["session_factory"]
    company_id = meli_test_context["company_id"]

    async with session_factory() as session:
        account = MeliAccount(
            company_id=company_id,
            meli_user_id=888111,
            nickname="Tienda-AutoRefresh",
            site_id="MLM",
            access_token_enc=encrypt_token("APP_USR-EXPIRED-TOKEN"),
            refresh_token_enc=encrypt_token("TG-VALID-REFRESH"),
            token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            is_active=True,
        )
        session.add(account)
        await session.commit()
        account_id = account.id

    async with session_factory() as session:
        connector = MercadoLibreConnector(account_id=account_id, db_session=session)

        # 1a llamada: responde 401 expired_token
        # 2a llamada (de refresh): responde 200 con nuevos tokens
        # 3a llamada (reintento): responde 200 con /users/me
        call_count = 0

        async def fake_request(client_self, method, url, **kwargs):
            nonlocal call_count
            call_count += 1
            if "/oauth/token" in str(url):
                return httpx.Response(
                    200,
                    json={
                        "access_token": "APP_USR-RENEWED-TOKEN",
                        "token_type": "bearer",
                        "expires_in": 21600,
                        "refresh_token": "TG-ROTATED-REFRESH",
                    },
                    request=httpx.Request(method, url),
                )
            if call_count == 1:
                return httpx.Response(
                    401,
                    json={"message": "expired_token", "error": "not_authorized", "status": 401},
                    request=httpx.Request(method, url),
                )
            return httpx.Response(
                200,
                json={"id": 888111, "nickname": "Tienda-AutoRefresh", "site_id": "MLM"},
                request=httpx.Request(method, url),
            )

        with patch("httpx.AsyncClient.request", new=fake_request):
            user_data = await connector.users.get_me()
            assert user_data["id"] == 888111
            assert user_data["nickname"] == "Tienda-AutoRefresh"

        # Verificar que en la BD se guardaron los nuevos tokens cifrados
        stmt = select(MeliAccount).where(MeliAccount.id == account_id)
        refreshed_acc = (await session.execute(stmt)).scalar_one()
        assert decrypt_token(refreshed_acc.access_token_enc) == "APP_USR-RENEWED-TOKEN"
        assert decrypt_token(refreshed_acc.refresh_token_enc) == "TG-ROTATED-REFRESH"


@pytest.mark.asyncio
async def test_rate_limiting_retry_behavior():
    """Simula una respuesta HTTP 429 de MeLi con retry-after; el conector debe reintentar."""
    connector = MercadoLibreConnector(app_id="123", client_secret="sec")
    connector._cached_access_token = "APP_USR-VALID"

    call_count = 0

    async def fake_request(client_self, method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "0.1", "x-ratelimit-remaining": "0"},
                json={"message": "Too Many Requests", "error": "rate_limit_exceeded"},
                request=httpx.Request(method, url),
            )
        return httpx.Response(
            200,
            json={"id": "MLM100", "title": "Producto Prueba"},
            request=httpx.Request(method, url),
        )

    with patch("httpx.AsyncClient.request", new=fake_request):
        item = await connector.items.get_item("MLM100")
        assert item["id"] == "MLM100"
        assert call_count == 2


# ==============================================================================
# 2. PRUEBAS DE MÓDULOS DE INTEGRACIÓN OFICIALES
# ==============================================================================


@pytest.mark.asyncio
async def test_users_and_items_integration_endpoints():
    """Prueba métodos del conector para Usuarios y Publicaciones."""
    connector = MercadoLibreConnector(app_id="123", client_secret="sec")
    connector._cached_access_token = "APP_USR-VALID"

    with patch("httpx.AsyncClient.request") as mock_req:
        # 1. Users get_user
        mock_req.return_value = httpx.Response(
            200,
            json={"id": 12345, "nickname": "COMPRADOR_MX"},
            request=httpx.Request("GET", "https://api.mercadolibre.com/users/12345"),
        )
        u = await connector.users.get_user(12345)
        assert u["nickname"] == "COMPRADOR_MX"

        # 2. Items search
        mock_req.return_value = httpx.Response(
            200,
            json={"seller_id": "123", "results": ["MLM101", "MLM102"], "paging": {"total": 2}},
            request=httpx.Request("GET", "https://api.mercadolibre.com/users/123/items/search"),
        )
        s = await connector.items.search_items(user_id=123, status="active")
        assert len(s["results"]) == 2

        # 3. Items multiget
        mock_req.return_value = httpx.Response(
            200,
            json=[
                {"code": 200, "body": {"id": "MLM101", "title": "Bocina 1"}},
                {"code": 200, "body": {"id": "MLM102", "title": "Bocina 2"}},
            ],
            request=httpx.Request("GET", "https://api.mercadolibre.com/items"),
        )
        items = await connector.items.get_items_multiget(["MLM101", "MLM102"])
        assert len(items) == 2

        # 4. Description update
        mock_req.return_value = httpx.Response(
            200,
            json={"plain_text": "Nueva descripción en texto plano"},
            request=httpx.Request("PUT", "https://api.mercadolibre.com/items/MLM101/description"),
        )
        desc = await connector.items.update_description("MLM101", "Nueva descripción en texto plano")
        assert desc["plain_text"] == "Nueva descripción en texto plano"


@pytest.mark.asyncio
async def test_variations_prices_and_inventory_endpoints():
    """Prueba métodos para Variantes, Precios e Inventario."""
    connector = MercadoLibreConnector(app_id="123", client_secret="sec")
    connector._cached_access_token = "APP_USR-VALID"

    with patch("httpx.AsyncClient.request") as mock_req:
        # 1. Update price
        mock_req.return_value = httpx.Response(
            200,
            json={"id": "MLM101", "price": 499.00},
            request=httpx.Request("PUT", "https://api.mercadolibre.com/items/MLM101"),
        )
        p = await connector.prices.update_price("MLM101", 499.00)
        assert p["price"] == 499.00

        # 2. Update stock
        mock_req.return_value = httpx.Response(
            200,
            json={"id": "MLM101", "available_quantity": 42},
            request=httpx.Request("PUT", "https://api.mercadolibre.com/items/MLM101"),
        )
        inv = await connector.inventory.update_stock("MLM101", 42)
        assert inv["available_quantity"] == 42

        # 3. Variations get
        mock_req.return_value = httpx.Response(
            200,
            json=[{"id": 111, "price": 499.0, "available_quantity": 20}],
            request=httpx.Request("GET", "https://api.mercadolibre.com/items/MLM101/variations"),
        )
        vars_res = await connector.variations.get_variations("MLM101")
        assert len(vars_res) == 1
        assert vars_res[0]["id"] == 111

        # 4. Stock fulfillment search
        mock_req.return_value = httpx.Response(
            200,
            json={"results": [{"inventory_id": "INV_FULL_1", "available_quantity": 100}]},
            request=httpx.Request("GET", "https://api.mercadolibre.com/stock/fulfillment/operations/search"),
        )
        full_stock = await connector.inventory.get_fulfillment_stock(seller_id=123)
        assert len(full_stock["results"]) == 1


@pytest.mark.asyncio
async def test_orders_shipments_and_promotions_endpoints():
    """Prueba métodos para Órdenes, Guías/Envíos y Promociones."""
    connector = MercadoLibreConnector(app_id="123", client_secret="sec")
    connector._cached_access_token = "APP_USR-VALID"

    with patch("httpx.AsyncClient.request") as mock_req:
        # 1. Search orders
        mock_req.return_value = httpx.Response(
            200,
            json={"results": [{"id": 200001, "status": "paid", "total_amount": 1250.0}]},
            request=httpx.Request("GET", "https://api.mercadolibre.com/orders/search"),
        )
        ords = await connector.orders.search_orders(seller_id=123, order_status="paid")
        assert ords["results"][0]["id"] == 200001

        # 2. Get shipment
        mock_req.return_value = httpx.Response(
            200,
            json={"id": 40001, "status": "ready_to_ship", "logistic_type": "fulfillment"},
            request=httpx.Request("GET", "https://api.mercadolibre.com/shipments/40001"),
        )
        shp = await connector.shipments.get_shipment(40001)
        assert shp["logistic_type"] == "fulfillment"

        # 3. Promotions
        mock_req.return_value = httpx.Response(
            200,
            json={"results": [{"id": "PROMO-HOT-SALE", "type": "DEAL", "status": "started"}]},
            request=httpx.Request("GET", "https://api.mercadolibre.com/seller-promotions/users/123"),
        )
        promos = await connector.promotions.get_seller_promotions(user_id=123)
        assert len(promos) == 1
        assert promos[0]["id"] == "PROMO-HOT-SALE"


# ==============================================================================
# 3. PRUEBAS DE ENDPOINTS REST DE ADMINISTRACIÓN DE CUENTAS
# ==============================================================================


def test_api_rest_meli_accounts_lifecycle(meli_test_context):
    """Comprueba el ciclo de vida completo vía API REST: alta, auth-url, diagnóstico, desconexión y reconexión."""
    client = meli_test_context["client"]
    headers = meli_test_context["headers"]
    company_id = meli_test_context["company_id"]

    # 1. Obtener Auth URL oficial
    res_url = client.get("/api/v1/meli-accounts/auth-url", headers=headers)
    assert res_url.status_code == 200
    assert "https://auth.mercadolibre.com.mx/authorization" in res_url.json()["auth_url"]
    assert "state=" in res_url.json()["auth_url"]

    # 2. Registrar cuenta con credenciales cifradas
    res_reg = client.post("/api/v1/meli-accounts", json={
        "company_id": company_id,
        "meli_user_id": 55443322,
        "nickname": "Tienda-Oficial-Audio-MX",
        "access_token_plain": "APP_USR-PLAIN-TOKEN-12345",
        "refresh_token_plain": "TG-PLAIN-REFRESH-67890",
        "expires_in_seconds": 21600,
    }, headers=headers)
    assert res_reg.status_code == 201
    account_id = res_reg.json()["id"]
    assert res_reg.json()["nickname"] == "Tienda-Oficial-Audio-MX"
    assert res_reg.json()["is_active"] is True

    # 3. Diagnóstico de conexión en vivo (simulando /users/me exitoso)
    with patch("httpx.AsyncClient.request") as mock_req:
        mock_req.return_value = httpx.Response(
            200,
            json={"id": 55443322, "nickname": "Tienda-Oficial-Audio-MX", "site_id": "MLM"},
            request=httpx.Request("GET", "https://api.mercadolibre.com/users/me"),
        )
        res_diag = client.post(f"/api/v1/meli-accounts/{account_id}/test-connection", headers=headers)
        assert res_diag.status_code == 200
        diag_data = res_diag.json()
        assert diag_data["healthy"] is True
        assert diag_data["latency_ms"] >= 0
        assert diag_data["nickname"] == "Tienda-Oficial-Audio-MX"

    # 4. Desconectar cuenta
    res_disc = client.post(f"/api/v1/meli-accounts/{account_id}/disconnect", headers=headers)
    assert res_disc.status_code == 200
    assert res_disc.json()["is_active"] is False

    # 5. Reconectar cuenta con nuevos tokens
    res_reconn = client.post(f"/api/v1/meli-accounts/{account_id}/reconnect", json={
        "access_token_plain": "APP_USR-NEW-PLAIN-9999",
        "refresh_token_plain": "TG-NEW-PLAIN-8888",
        "expires_in_seconds": 21600,
    }, headers=headers)
    assert res_reconn.status_code == 200
    assert res_reconn.json()["is_active"] is True


def test_api_rest_delegated_connector_actions(meli_test_context):
    """Comprueba las llamadas delegadas de stock, precio y órdenes vía API REST."""
    client = meli_test_context["client"]
    headers = meli_test_context["headers"]
    company_id = meli_test_context["company_id"]

    # Registrar cuenta activa
    res_reg = client.post("/api/v1/meli-accounts", json={
        "company_id": company_id,
        "meli_user_id": 77665544,
        "nickname": "Tienda-Delegada",
        "access_token_plain": "APP_USR-TOKEN-ABC",
        "refresh_token_plain": "TG-REFRESH-DEF",
        "expires_in_seconds": 21600,
    }, headers=headers)
    assert res_reg.status_code == 201
    account_id = res_reg.json()["id"]

    with patch("httpx.AsyncClient.request") as mock_req:
        # 1. Actualizar stock
        mock_req.return_value = httpx.Response(
            200,
            json={"id": "MLM999", "available_quantity": 25},
            request=httpx.Request("PUT", "https://api.mercadolibre.com/items/MLM999"),
        )
        res_stock = client.put(
            f"/api/v1/meli-accounts/{account_id}/items/MLM999/stock",
            json={"available_quantity": 25},
            headers=headers,
        )
        assert res_stock.status_code == 200
        assert res_stock.json()["available_quantity"] == 25

        # 2. Actualizar precio
        mock_req.return_value = httpx.Response(
            200,
            json={"id": "MLM999", "price": 899.00},
            request=httpx.Request("PUT", "https://api.mercadolibre.com/items/MLM999"),
        )
        res_price = client.put(
            f"/api/v1/meli-accounts/{account_id}/items/MLM999/price",
            json={"price": 899.00},
            headers=headers,
        )
        assert res_price.status_code == 200
        assert res_price.json()["price"] == 899.00
