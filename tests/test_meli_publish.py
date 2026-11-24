"""Pruebas de la publicación de productos en Mercado Libre desde el ERP.

Cubre el endpoint POST /api/v1/products/{product_id}/publish-meli:
- Crea la publicación con POST /items (conector mockeado: NUNCA toca la API
  real de Mercado Libre, para no crear publicaciones de verdad).
- Guarda la descripción y deja el mapeo variante <-> publicación (ProductSKU).
- Valida título (máx. 60), fotos obligatorias y propaga el error oficial de MeLi.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.connectors.meli.exceptions import MeliAPIException
from src.core.database import get_db
from src.core.security import encrypt_token
from src.main import app
from src.models import Base
from src.models.meli_account import MeliAccount


class FakeItemsClient:
    """Imita MeliItemsClient sin tocar la red."""

    def __init__(self, fail_create_with: MeliAPIException | None = None):
        self.created_payloads: list[dict] = []
        self.descriptions: dict[str, str] = {}
        self._fail_create_with = fail_create_with

    async def create_item(self, payload: dict) -> dict:
        if self._fail_create_with is not None:
            raise self._fail_create_with
        self.created_payloads.append(payload)
        return {
            "id": "MLM1234567890",
            "permalink": "https://articulo.mercadolibre.com.mx/MLM-1234567890-test",
            "status": "active",
        }

    async def update_description(self, item_id: str, plain_text: str) -> dict:
        self.descriptions[item_id] = plain_text
        return {}


class FakeConnector:
    """Imita MercadoLibreConnector con un cliente de items falso."""

    def __init__(self, *args, **kwargs):
        self.items = FakeItemsClient()

    async def check_and_proactively_refresh(self):
        return None


@pytest.fixture
def publish_context(tmp_path, monkeypatch):
    """Cliente HTTP con tenant/empresa/token válidos y una cuenta MeLi vinculada."""
    db_file = tmp_path / "meli_publish_test.db"
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
        reg_res = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Publish {unique_id}",
            "tenant_slug": f"pub-slug-{unique_id}",
            "company_legal_name": f"Empresa Publish S.A. {unique_id}",
            "company_rfc": "PUB991201AB0",
            "admin_email": f"admin_pub_{unique_id}@test.com",
            "admin_password": "PasswordPub1!",
            "admin_full_name": "Admin Publish",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        login_res = client.post("/api/v1/auth/login", json={
            "email": f"admin_pub_{unique_id}@test.com",
            "password": "PasswordPub1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "X-Company-ID": company_id}

        # Cuenta MeLi vinculada (tokens cifrados de prueba; el conector real
        # nunca se construye porque el test lo sustituye por el falso).
        async def _insert_account():
            async with session_factory() as session:
                account = MeliAccount(
                    company_id=uuid.UUID(company_id),
                    meli_user_id=999888777,
                    nickname="TESTPUBLISHER",
                    access_token_enc=encrypt_token("APP_USR-TEST-ACCESS"),
                    refresh_token_enc=encrypt_token("TG-TEST-REFRESH"),
                    token_expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
                    is_active=True,
                )
                session.add(account)
                await session.commit()
                return str(account.id)

        account_id = asyncio.run(_insert_account())

        yield client, company_id, headers, account_id, session_factory

    app.dependency_overrides.pop(get_db, None)


def _create_charger_product(client, company_id, headers, *, with_images=True):
    payload = {
        "company_id": company_id,
        "name": "Cargador USB-C 2 en 1 PD 20W Doble Puerto",
        "brand": "Ele-Gate",
        "model": "CH.102",
        "category": "Cargadores de dispositivos móviles",
        "category_code": "MLM1234",
        "description": "Cargador de pared 2 en 1: puerto USB-C PD de 20W y puerto USB de 10W.",
        "cost_price": 48.00,
        "sale_price": 129.00,
        "images": (
            ["https://img.ele-gate.com/CH.102-3.jpg", "https://img.ele-gate.com/CH.102-2.jpg"]
            if with_images
            else []
        ),
        "variants": [
            {
                "variant_name": "Blanco",
                "sku": "CH.102-BLC",
                "barcode_ean": "07503050554934",
                "cogs_cost": 48.00,
                "sale_price": 129.00,
                "attributes": {"color": "Blanco"},
            }
        ],
    }
    res = client.post("/api/v1/products", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_publish_creates_meli_item_description_and_mapping(publish_context, monkeypatch):
    """Publicar crea el item en MeLi, guarda la descripción y mapea la variante."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)

    fake = FakeConnector()
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: fake,
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={"meli_account_id": account_id, "category_id": "MLM1234"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["meli_item_id"] == "MLM1234567890"
    assert body["permalink"].startswith("https://articulo.mercadolibre.com.mx/MLM-1234567890")
    assert body["price"] == 129.00
    assert body["listing_type_id"] == "free"
    assert body["description_error"] is None

    # El payload enviado a MeLi lleva lo que el flujo web pedía a mano.
    assert len(fake.items.created_payloads) == 1
    sent = fake.items.created_payloads[0]
    # En el modelo User Products de MeLi NO se manda "title": el título lo
    # compone Mercado Libre a partir de family_name + atributos; mandar
    # "title" hace que POST /items responda body.invalid_fields
    # ("The fields [title] are invalid for requested call.", caso real
    # 2026-11-23 con HW001). El campo del modal sigue siendo el nombre del
    # producto, que viaja como family_name.
    assert "title" not in sent
    # family_name: MeLi lo exige en categorías con dominio de catálogo
    # (sin él, POST /items responde body.required_fields).
    assert sent["family_name"] == "Cargador USB-C 2 en 1 PD 20W Doble Puerto"
    assert sent["category_id"] == "MLM1234"
    assert sent["price"] == 129.00
    assert sent["currency_id"] == "MXN"
    assert sent["listing_type_id"] == "free"
    assert sent["buying_mode"] == "buy_it_now"
    assert sent["condition"] == "new"
    assert sent["available_quantity"] == 1
    assert sent["pictures"] == [
        {"source": "https://img.ele-gate.com/CH.102-3.jpg"},
        {"source": "https://img.ele-gate.com/CH.102-2.jpg"},
    ]
    assert sent["shipping"]["mode"] == "me2"
    attrs = {a["id"]: a["value_name"] for a in sent["attributes"]}
    assert attrs["BRAND"] == "Ele-Gate"
    assert attrs["MODEL"] == "CH.102"
    assert attrs["GTIN"] == "07503050554934"
    assert attrs["COLOR"] == "Blanco"
    assert {"id": "WARRANTY_TYPE", "value_name": "Garantía de fábrica"} in sent["sale_terms"]
    assert {"id": "WARRANTY_TIME", "value_name": "90 días"} in sent["sale_terms"]

    # Descripción guardada por el endpoint separado de MeLi.
    assert fake.items.descriptions["MLM1234567890"].startswith("Cargador de pared 2 en 1")

    # El mapeo variante <-> publicación quedó registrado en el ERP.
    mappings = client.get(f"/api/v1/products/{product['id']}/mappings", headers=headers)
    assert mappings.status_code == 200, mappings.text
    assert len(mappings.json()) == 1
    assert mappings.json()[0]["meli_item_id"] == "MLM1234567890"


def test_publish_rejects_title_over_60_chars(publish_context, monkeypatch):
    """MeLi acepta máximo 60 caracteres en el título: el ERP lo valida antes."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: FakeConnector(),
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={
            "meli_account_id": account_id,
            "category_id": "MLM1234",
            "title": "X" * 61,
        },
        headers=headers,
    )
    # El esquema rechaza el título largo antes de llegar al servicio (422).
    assert res.status_code == 422
    assert res.json()["code"] == "VALIDATION_ERROR"


def test_publish_requires_at_least_one_picture(publish_context, monkeypatch):
    """Sin fotos no se puede publicar: MeLi las exige."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers, with_images=False)
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: FakeConnector(),
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={"meli_account_id": account_id, "category_id": "MLM1234"},
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["code"] == "VALIDATION_ERROR"


def test_publish_surfaces_meli_official_error(publish_context, monkeypatch):
    """Si MeLi rechaza la publicación (p. ej. propiedad intelectual), el error
    oficial llega tal cual al cliente en lugar de un 500 genérico."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)

    failing = FakeConnector()
    failing.items = FakeItemsClient(
        fail_create_with=MeliAPIException(
            "invalid item: intellectual property infringement",
            status_code=400,
            error_code="invalid_item",
            cause=[{"code": "IP", "message": "intellectual property"}],
        )
    )
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: failing,
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={"meli_account_id": account_id, "category_id": "MLM1234"},
        headers=headers,
    )
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "MELI_PUBLISH_ERROR"
    assert "intellectual property" in body["error"]


def test_publish_surfaces_meli_cause_detail(publish_context, monkeypatch):
    """Si MeLi rechaza con body.required_fields, el 'cause' oficial (que nombra
    el campo faltante) llega en el mensaje en lugar de quedarse solo en details."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)

    failing = FakeConnector()
    failing.items = FakeItemsClient(
        fail_create_with=MeliAPIException(
            "body.required_fields",
            status_code=400,
            error_code="bad_request",
            cause=[{"code": "body.required_fields", "description": "Field required: description"}],
        )
    )
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: failing,
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={"meli_account_id": account_id, "category_id": "MLM1234"},
        headers=headers,
    )
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "MELI_PUBLISH_ERROR"
    assert "body.required_fields" in body["error"]
    assert "Field required: description" in body["error"]


def test_publish_sends_extra_attributes_with_value_id(publish_context, monkeypatch):
    """Los atributos extra del request viajan tal cual (con value_id y
    value_name) en el "attributes" del POST /items. Caso real 2026-11-23:
    MLM429747 (Cargadores para Celulares) exige CONNECTOR_TYPE ("Tipo de
    conector") y sin él MeLi responde 400 "The attributes [CONNECTOR_TYPE]
    are required for category MLM429747..."."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)

    fake = FakeConnector()
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: fake,
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={
            "meli_account_id": account_id,
            "category_id": "MLM429747",
            "attributes": [
                {"id": "CONNECTOR_TYPE", "value_id": "2113108", "value_name": "USB-C"}
            ],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text

    assert len(fake.items.created_payloads) == 1
    sent = fake.items.created_payloads[0]
    # family_name sigue siendo el título y "title" NO se manda (fix 8).
    assert "title" not in sent
    assert sent["family_name"] == "Cargador USB-C 2 en 1 PD 20W Doble Puerto"
    assert sent["category_id"] == "MLM429747"
    # El atributo extra llega íntegro, sin perder el value_id del catálogo.
    assert {
        "id": "CONNECTOR_TYPE",
        "value_id": "2113108",
        "value_name": "USB-C",
    } in sent["attributes"]
    # Los atributos automáticos (BRAND/MODEL/GTIN/COLOR) siguen presentes.
    attrs = {a["id"]: a.get("value_name") for a in sent["attributes"]}
    assert attrs["BRAND"] == "Ele-Gate"
    assert attrs["GTIN"] == "07503050554934"


def test_publish_attribute_with_only_value_id(publish_context, monkeypatch):
    """Un atributo de catálogo puede venir solo con value_id (sin value_name)
    y se pasa tal cual a MeLi."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)

    fake = FakeConnector()
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: fake,
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={
            "meli_account_id": account_id,
            "category_id": "MLM429747",
            "attributes": [{"id": "CONNECTOR_TYPE", "value_id": "2113108"}],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text
    sent = fake.items.created_payloads[0]
    assert {"id": "CONNECTOR_TYPE", "value_id": "2113108"} in sent["attributes"]


def test_publish_attribute_without_any_value_is_rejected(publish_context, monkeypatch):
    """Un atributo sin value_id ni value_name no dice nada: el esquema lo
    rechaza con 422 antes de llegar a MeLi."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: FakeConnector(),
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={
            "meli_account_id": account_id,
            "category_id": "MLM429747",
            "attributes": [{"id": "CONNECTOR_TYPE"}],
        },
        headers=headers,
    )
    assert res.status_code == 422
    assert res.json()["code"] == "VALIDATION_ERROR"


def test_publish_without_attributes_unchanged(publish_context, monkeypatch):
    """Sin atributos extra, el payload es exactamente el de antes (fix 8):
    solo los 4 automáticos, family_name y sin "title"."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)

    fake = FakeConnector()
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: fake,
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={"meli_account_id": account_id, "category_id": "MLM1234"},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    sent = fake.items.created_payloads[0]
    assert "title" not in sent
    assert sent["family_name"] == "Cargador USB-C 2 en 1 PD 20W Doble Puerto"
    assert {a["id"] for a in sent["attributes"]} == {"BRAND", "MODEL", "GTIN", "COLOR"}


def test_publish_surfaces_meli_error_code_when_cause_is_empty(publish_context, monkeypatch):
    """En body.invalid_fields MeLi devuelve cause=[] y el campo inválido vive
    en 'error' (p. ej. "The fields [title] are invalid..."): ese detalle debe
    llegar al mensaje, si no el cuadro rojo no nombra el campo (caso real
    2026-11-23: HW001, error [title])."""
    client, company_id, headers, account_id, _factory = publish_context
    product = _create_charger_product(client, company_id, headers)

    failing = FakeConnector()
    failing.items = FakeItemsClient(
        fail_create_with=MeliAPIException(
            "body.invalid_fields",
            status_code=400,
            error_code="The fields [title] are invalid for requested call.",
            cause=[],
        )
    )
    monkeypatch.setattr(
        "src.services.catalog_service.MercadoLibreConnector",
        lambda *args, **kwargs: failing,
    )

    res = client.post(
        f"/api/v1/products/{product['id']}/publish-meli",
        json={"meli_account_id": account_id, "category_id": "MLM1234"},
        headers=headers,
    )
    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "MELI_PUBLISH_ERROR"
    assert "body.invalid_fields" in body["error"]
    assert "The fields [title] are invalid" in body["error"]
