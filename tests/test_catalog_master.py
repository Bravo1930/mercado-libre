"""Pruebas exhaustivas para el Catálogo Maestro de Productos del ERP."""

import io
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.database import get_db
from src.main import app
from src.models import Base


@pytest.fixture
def catalog_context(tmp_path):
    """Provee un cliente HTTP configurado con tenant, empresa y token de autenticación válido."""
    db_file = tmp_path / "catalog_master_test.db"
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
        # Registrar Tenant y Empresa inicial
        unique_id = uuid.uuid4().hex[:6]
        reg_res = client.post("/api/v1/auth/register-tenant", json={
            "tenant_name": f"Tenant Catalogo {unique_id}",
            "tenant_slug": f"cat-slug-{unique_id}",
            "company_legal_name": f"Empresa Catalogo S.A. {unique_id}",
            "company_rfc": "CAT991201AB0",
            "admin_email": f"admin_cat_{unique_id}@test.com",
            "admin_password": "PasswordCat1!",
            "admin_full_name": "Admin Catalogo",
        })
        assert reg_res.status_code == 201
        company_id = reg_res.json()["company_id"]

        # Iniciar sesión para obtener JWT con sesión activa en DB
        login_res = client.post("/api/v1/auth/login", json={
            "email": f"admin_cat_{unique_id}@test.com",
            "password": "PasswordCat1!",
        })
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Company-ID": company_id,
        }

        yield client, company_id, headers

    app.dependency_overrides.pop(get_db, None)


def test_create_and_edit_master_product_with_full_specs(catalog_context):
    """Comprueba el alta y edición completa de un producto maestro con peso, dimensiones y auditoría."""
    client, company_id, headers = catalog_context

    payload = {
        "company_id": company_id,
        "name": "Bocina Bluetooth Resistente al Agua",
        "brand": "SoundBox",
        "model": "SB-EXPLORE-2026",
        "category": "Audio > Bocinas Portátiles",
        "category_code": "MLM1055",
        "description": "Bocina inalámbrica sumergible IPX7 con batería de 24 horas y bajos reforzados.",
        "short_description": "Bocina Bluetooth sumergible IPX7",
        "unit_of_measure": "H87",
        "cost_price": 350.00,
        "last_cost": 340.00,
        "sale_price": 899.00,
        "wholesale_price": 720.00,
        "min_price": 650.00,
        "weight_kg": 0.650,
        "length_cm": 18.5,
        "width_cm": 7.5,
        "height_cm": 7.5,
        "warehouse_location": "Pasillo 4 - Rack C - Gaveta 12",
        "images": ["https://img.com/bocina1.jpg", "https://img.com/bocina2.jpg"],
        "variants": [
            {
                "variant_name": "Negro Carbón",
                "sku": "SB-EXP-BLK",
                "barcode_ean": "7501000000014",
                "cogs_cost": 350.00,
                "sale_price": 899.00,
                "attributes": {"color": "Negro"},
            },
            {
                "variant_name": "Azul Marino",
                "sku": "SB-EXP-BLU",
                "barcode_ean": "7501000000021",
                "cogs_cost": 350.00,
                "sale_price": 899.00,
                "attributes": {"color": "Azul"},
            },
        ],
    }

    # Alta
    res = client.post("/api/v1/products", json=payload, headers=headers)
    assert res.status_code == 201
    prod = res.json()
    assert prod["name"] == "Bocina Bluetooth Resistente al Agua"
    assert prod["brand"] == "SoundBox"
    assert prod["weight_kg"] == 0.65
    assert len(prod["variants"]) == 2
    prod_id = prod["id"]

    # Edición
    update_payload = {
        "sale_price": 949.00,
        "wholesale_price": 750.00,
        "warehouse_location": "Pasillo 4 - Rack C - Gaveta 15 (Reubicado)",
    }
    update_res = client.put(f"/api/v1/products/{prod_id}", json=update_payload, headers=headers)
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["sale_price"] == 949.00
    assert "Reubicado" in updated["warehouse_location"]


def test_sku_uniqueness_per_company(catalog_context):
    """Comprueba que no se permitan SKUs duplicados dentro de la misma empresa."""
    client, company_id, headers = catalog_context

    # 1. Crear producto con SKU 'SKU-UNIQUE-001'
    payload1 = {
        "company_id": company_id,
        "name": "Producto A",
        "variants": [
            {
                "variant_name": "Variante 1",
                "sku": "SKU-UNIQUE-001",
                "cogs_cost": 100.0,
            }
        ],
    }
    res1 = client.post("/api/v1/products", json=payload1, headers=headers)
    assert res1.status_code == 201

    # 2. Intentar crear otro producto con el MISMO SKU en la misma empresa
    payload2 = {
        "company_id": company_id,
        "name": "Producto B con SKU duplicado",
        "variants": [
            {
                "variant_name": "Variante Conflicto",
                "sku": "SKU-UNIQUE-001",  # Duplicado
                "cogs_cost": 200.0,
            }
        ],
    }
    res2 = client.post("/api/v1/products", json=payload2, headers=headers)
    assert res2.status_code == 409
    err_msg = res2.json().get("error", "")
    assert "SKU 'SKU-UNIQUE-001' ya está registrado" in err_msg


def test_toggle_product_status_and_soft_delete(catalog_context):
    """Comprueba la desactivación y reactivación de productos y sus variantes."""
    client, company_id, headers = catalog_context

    payload = {
        "company_id": company_id,
        "name": "Producto a Desactivar",
        "variants": [{"variant_name": "Unica", "sku": "SKU-DESACT-01"}],
    }
    res = client.post("/api/v1/products", json=payload, headers=headers)
    prod_id = res.json()["id"]

    # Desactivar
    toggle_res = client.patch(f"/api/v1/products/{prod_id}/toggle-status", headers=headers)
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] is False

    # Reactivar explícitamente
    activate_res = client.patch(f"/api/v1/products/{prod_id}/toggle-status?is_active=true", headers=headers)
    assert activate_res.status_code == 200
    assert activate_res.json()["is_active"] is True


def test_search_by_sku_barcode_and_name(catalog_context):
    """Comprueba la búsqueda multicriterio por nombre, SKU y código de barras."""
    client, company_id, headers = catalog_context

    client.post(
        "/api/v1/products",
        json={
            "company_id": company_id,
            "name": "Teclado Mecánico RGB Gamer",
            "brand": "HyperKey",
            "variants": [
                {"variant_name": "Switches Blue", "sku": "HK-MECH-BLU", "barcode_ean": "7509876543210"}
            ],
        },
        headers=headers,
    )

    # Buscar por SKU en query global 'q'
    search_sku = client.get("/api/v1/products?q=HK-MECH-BLU", headers=headers)
    assert search_sku.status_code == 200
    assert len(search_sku.json()["items"]) == 1

    # Buscar por código de barras específico
    search_barcode = client.get("/api/v1/products?barcode=7509876543210", headers=headers)
    assert search_barcode.status_code == 200
    assert len(search_barcode.json()["items"]) == 1

    # Buscar por nombre parcial
    search_name = client.get("/api/v1/products?q=Teclado", headers=headers)
    assert search_name.status_code == 200
    assert len(search_name.json()["items"]) >= 1


def test_import_meli_products_anti_duplicate_flow(catalog_context):
    """Comprueba la importación desde Mercado Libre evitando crear duplicados si el SKU ya existe."""
    client, company_id, headers = catalog_context

    # Crear cuenta MeLi asociada vía endpoint
    meli_acc_res = client.post("/api/v1/meli-accounts", json={
        "company_id": company_id,
        "meli_user_id": 9988776655,
        "nickname": "TiendaOficialMeLiTest",
        "access_token_plain": "APP_USR-TEST",
        "refresh_token_plain": "TG-TEST",
        "expires_in_seconds": 21600,
    }, headers=headers)
    assert meli_acc_res.status_code == 201
    account_id = meli_acc_res.json()["id"]

    import_payload = {
        "meli_account_id": account_id,
        "items": [
            {
                "id": "MLM1122334455",
                "title": "Mouse Ergonómico Inalámbrico Vertical",
                "seller_custom_field": "MOUSE-ERG-VERT",
                "price": 450.00,
                "brand": "ErgoTech",
                "model": "EV-300",
                "barcode_ean": "7505556667778",
                "pictures": ["https://meli.com/mouse.jpg"],
            }
        ],
    }

    # 1. Primera importación -> debe CREAR
    first_import = client.post("/api/v1/products/import-meli", json=import_payload, headers=headers)
    assert first_import.status_code == 200
    data1 = first_import.json()
    assert data1["created"] == 1
    assert data1["updated"] == 0
    assert data1["linked_mappings"] == 1

    # 2. Segunda importación con mismo ID y SKU pero precio actualizado -> debe ACTUALIZAR sin duplicar
    import_payload["items"][0]["price"] = 499.00
    second_import = client.post("/api/v1/products/import-meli", json=import_payload, headers=headers)
    assert second_import.status_code == 200
    data2 = second_import.json()
    assert data2["created"] == 0
    assert data2["updated"] == 1

    # Verificar que solo exista UN producto en el catálogo
    check_res = client.get("/api/v1/products?sku=MOUSE-ERG-VERT", headers=headers)
    items = check_res.json()["items"]
    assert len(items) == 1
    assert items[0]["sale_price"] == 499.00


def test_multi_publication_mapping_per_product(catalog_context):
    """Comprueba que un producto interno pueda relacionarse con múltiples publicaciones MeLi y cuentas."""
    client, company_id, headers = catalog_context

    # Dos cuentas MeLi de la misma empresa
    acc1_res = client.post("/api/v1/meli-accounts", json={
        "company_id": company_id,
        "meli_user_id": 11111111,
        "nickname": "Cuenta Clásica",
        "access_token_plain": "T1",
        "refresh_token_plain": "R1",
        "expires_in_seconds": 21600,
    }, headers=headers)
    acc2_res = client.post("/api/v1/meli-accounts", json={
        "company_id": company_id,
        "meli_user_id": 22222222,
        "nickname": "Cuenta Premium",
        "access_token_plain": "T2",
        "refresh_token_plain": "R2",
        "expires_in_seconds": 21600,
    }, headers=headers)
    assert acc1_res.status_code == 201
    assert acc2_res.status_code == 201
    acc1_id = acc1_res.json()["id"]
    acc2_id = acc2_res.json()["id"]

    # Crear producto
    p_res = client.post(
        "/api/v1/products",
        json={
            "company_id": company_id,
            "name": "Funda iPhone 15 Pro Max Cuero",
            "variants": [{"variant_name": "Negro", "sku": "CASE-IP15PM-BLK"}],
        },
        headers=headers,
    )
    prod = p_res.json()
    prod_id = prod["id"]
    variant_id = prod["variants"][0]["id"]

    # Mapear a Publicación 1 en Cuenta 1 (Clásica)
    map1_res = client.post(
        "/api/v1/products/mappings",
        json={
            "meli_account_id": acc1_id,
            "variant_id": variant_id,
            "meli_item_id": "MLM5001",
            "seller_sku": "CASE-IP15PM-BLK",
            "price": 399.00,
            "listing_type_id": "gold_special",
        },
        headers=headers,
    )
    assert map1_res.status_code == 201

    # Mapear a Publicación 2 en Cuenta 2 (Premium con envío FULL)
    map2_res = client.post(
        "/api/v1/products/mappings",
        json={
            "meli_account_id": acc2_id,
            "variant_id": variant_id,
            "meli_item_id": "MLM5002",
            "seller_sku": "CASE-IP15PM-BLK",
            "price": 449.00,
            "listing_type_id": "gold_pro",
            "logistic_type": "fulfillment",
        },
        headers=headers,
    )
    assert map2_res.status_code == 201

    # Consultar mapeos asociados a este producto
    mappings_res = client.get(f"/api/v1/products/{prod_id}/mappings", headers=headers)
    assert mappings_res.status_code == 200
    mappings = mappings_res.json()
    assert len(mappings) == 2
    item_ids = {m["meli_item_id"] for m in mappings}
    assert "MLM5001" in item_ids
    assert "MLM5002" in item_ids


def test_import_and_export_csv_and_xlsx(catalog_context):
    """Comprueba la importación por CSV y las descargas oficiales en CSV y XLSX."""
    client, _, headers = catalog_context

    # 1. Importar CSV
    csv_data = (
        "sku,nombre,marca,modelo,categoria,codigobarras,costo,precio,peso_kg\n"
        "CSV-PROD-01,Hub USB-C 7 en 1,Anker,A8346,Computo,7509998881112,280.00,599.00,0.150\n"
        "CSV-PROD-02,Microfono Condensador USB,Rode,NT-USB,Audio,7509998882223,1200.00,2499.00,0.850\n"
    )
    files = {"file": ("test_catalogo.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
    import_res = client.post("/api/v1/products/import-csv", files=files, headers=headers)
    assert import_res.status_code == 200
    res_json = import_res.json()
    assert res_json["created"] == 2
    assert len(res_json["errors"]) == 0

    # 2. Exportar CSV
    export_csv_res = client.get("/api/v1/products/export-csv", headers=headers)
    assert export_csv_res.status_code == 200
    assert "text/csv" in export_csv_res.headers["content-type"]
    assert "CSV-PROD-01" in export_csv_res.text
    assert "Microfono Condensador USB" in export_csv_res.text

    # 3. Exportar XLSX
    export_xlsx_res = client.get("/api/v1/products/export-xlsx", headers=headers)
    assert export_xlsx_res.status_code == 200
    assert "spreadsheetml.sheet" in export_xlsx_res.headers["content-type"]
    assert len(export_xlsx_res.content) > 1000  # Archivo binario XLSX válido


def test_detect_duplicates_endpoint(catalog_context):
    """Comprueba el reporte de detección de duplicados por código de barras o nombres similares."""
    client, company_id, headers = catalog_context

    # Crear dos productos distintos pero con el MISMO código de barras EAN
    shared_ean = "7501112223334"
    client.post(
        "/api/v1/products",
        json={
            "company_id": company_id,
            "name": "Cargador Rápido 20W USB-C Versión A",
            "variants": [{"variant_name": "A", "sku": "CHG-20W-A", "barcode_ean": shared_ean}],
        },
        headers=headers,
    )
    client.post(
        "/api/v1/products",
        json={
            "company_id": company_id,
            "name": "Cargador Rápido 20W USB-C Versión B",
            "variants": [{"variant_name": "B", "sku": "CHG-20W-B", "barcode_ean": shared_ean}],
        },
        headers=headers,
    )

    dup_res = client.get("/api/v1/products/duplicates", headers=headers)
    assert dup_res.status_code == 200
    dup_data = dup_res.json()
    assert dup_data["total_groups"] >= 1
    barcode_group = next((g for g in dup_data["duplicate_groups"] if g["key_value"] == shared_ean), None)
    assert barcode_group is not None
    assert len(barcode_group["candidates"]) == 2
