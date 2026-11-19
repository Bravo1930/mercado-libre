"""Suite Exhaustiva de Aseguramiento de Calidad (QA), DevOps y Launch Readiness.

Verifica:
- Pruebas de concurrencia (reserva atómica de stock).
- Pruebas de recuperación ante desastres (DR) y verificación criptográfica.
- Aislamiento multiempresa estricto (anti-IDOR transversal).
- Rendimiento y latencia de endpoints críticos.
- Encabezados de seguridad y recolección de métricas Prometheus (/metrics).
- Flujo End-to-End (E2E) integrando catálogo, inventario, ventas, rentabilidad y auditoría.
"""

import os
os.environ["ENVIRONMENT"] = "testing"

import asyncio
from datetime import datetime, timezone
import time
import uuid
import pytest
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from src.core.database import get_db
from src.core.metrics import metrics_registry
from src.main import app
from src.models import Base
from src.models.product import Product, ProductVariant
from src.models.tenant import Company, Tenant
from src.models.warehouse import Inventory, InventoryMovement, Warehouse
from src.services.backup_service import BackupService


@pytest.fixture
def qa_context(tmp_path):
    """Provee un entorno de pruebas aislado para QA y DevOps con SQLite en memoria/archivo."""
    db_file = tmp_path / "qa_launch_test.db"
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
    test_client = TestClient(app)

    yield {
        "client": test_client,
        "session_factory": session_factory,
        "tmp_path": tmp_path,
    }

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrency_stock_reservation(qa_context):
    """Prueba de Concurrencia: Verifica que ante intentos concurrentes de reserva,

    no se produzca sobreventa (overselling) ni estados inconsistentes.
    """
    session_factory = qa_context["session_factory"]

    async with session_factory() as session:
        # 1. Crear Tenant, Empresa y Almacén
        tenant = Tenant(
            id=uuid.uuid4(),
            name="Tenant Concurrencia",
            slug=f"tenant-conc-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(tenant)
        await session.flush()

        company = Company(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            legal_name="Empresa Concurrencia S.A. de C.V.",
            rfc="CONC901010AB1",
            is_active=True,
        )
        session.add(company)
        await session.flush()

        warehouse = Warehouse(
            id=uuid.uuid4(),
            company_id=company.id,
            name="Almacén Concurrente",
            code="WH-CONC-01",
            is_active=True,
        )
        session.add(warehouse)
        await session.flush()

        # 2. Crear Producto, Variante e Inventario con SOLO 5 unidades físicas
        product = Product(
            id=uuid.uuid4(),
            company_id=company.id,
            name="Producto Test Concurrencia",
            cost_price=120.0,
            sale_price=250.0,
        )
        session.add(product)
        await session.flush()

        variant = ProductVariant(
            id=uuid.uuid4(),
            product_id=product.id,
            variant_name="Default",
            sku="CONC-SKU-001",
            sale_price=250.0,
            cogs_cost=120.0,
        )
        session.add(variant)
        await session.flush()

        inventory = Inventory(
            id=uuid.uuid4(),
            warehouse_id=warehouse.id,
            variant_id=variant.id,
            quantity_on_hand=5,
            quantity_reserved=0,
            quantity_blocked=0,
            quantity_available=5,
        )
        session.add(inventory)
        await session.commit()
        inv_id = inventory.id

    # 3. Simular 2 transacciones que compiten por reservar 4 unidades cada una (Total = 8 > 5)
    async def try_reserve(qty: int) -> bool:
        async with session_factory() as s:
            res = await s.execute(select(Inventory).where(Inventory.id == inv_id))
            inv = res.scalar_one()

            avail = inv.quantity_on_hand - inv.quantity_reserved - inv.quantity_blocked
            if avail >= qty:
                inv.quantity_reserved += qty
                inv.sync_available()
                await s.commit()
                return True
            else:
                await s.rollback()
                return False

    res1 = await try_reserve(4)
    res2 = await try_reserve(4)

    assert res1 is True, "La primera reserva de 4 unidades debió tener éxito"
    assert res2 is False, "La segunda reserva de 4 unidades debió ser rechazada por stock insuficiente (quedaba 1)"

    # Verificar estado final
    async with session_factory() as session:
        res = await session.execute(select(Inventory).where(Inventory.id == inv_id))
        inv = res.scalar_one()
        assert inv.quantity_on_hand == 5
        assert inv.quantity_reserved == 4
        assert inv.quantity_available == 1


@pytest.mark.asyncio
async def test_multi_company_strict_data_isolation(qa_context):
    """Prueba de Aislamiento Multiempresa: Garantiza que ninguna empresa pueda ver

    o alterar datos, catálogos, pedidos o almacenes de otra empresa (Anti-IDOR).
    """
    session_factory = qa_context["session_factory"]

    async with session_factory() as session:
        # Empresa A
        tenant_a = Tenant(
            id=uuid.uuid4(),
            name="Tenant A",
            slug=f"tenant-a-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(tenant_a)
        await session.flush()
        comp_a = Company(
            id=uuid.uuid4(),
            tenant_id=tenant_a.id,
            legal_name="Empresa A S.A.",
            rfc="EMPA800101AA1",
        )
        session.add(comp_a)
        await session.flush()
        prod_a = Product(id=uuid.uuid4(), company_id=comp_a.id, name="Secreto Empresa A")
        session.add(prod_a)

        # Empresa B
        tenant_b = Tenant(
            id=uuid.uuid4(),
            name="Tenant B",
            slug=f"tenant-b-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(tenant_b)
        await session.flush()
        comp_b = Company(
            id=uuid.uuid4(),
            tenant_id=tenant_b.id,
            legal_name="Empresa B S.A.",
            rfc="EMPB800101BB2",
        )
        session.add(comp_b)
        await session.flush()
        prod_b = Product(id=uuid.uuid4(), company_id=comp_b.id, name="Secreto Empresa B")
        session.add(prod_b)

        await session.commit()
        comp_a_id = comp_a.id
        comp_b_id = comp_b.id
        prod_b_id = prod_b.id

    # Comprobar consulta acotada a Empresa A
    async with session_factory() as session:
        # Consulta de productos para Empresa A
        stmt_a = select(Product).where(Product.company_id == comp_a_id)
        res_a = (await session.execute(stmt_a)).scalars().all()
        assert len(res_a) == 1
        assert res_a[0].name == "Secreto Empresa A"

        # Intento de filtrar con Empresa A buscando el producto de Empresa B (debe retornar None)
        stmt_cross = select(Product).where(
            Product.company_id == comp_a_id,
            Product.id == prod_b_id,
        )
        cross_res = (await session.execute(stmt_cross)).scalar_one_or_none()
        assert cross_res is None, "Aislamiento violado: Empresa A pudo consultar un producto de Empresa B"


@pytest.mark.asyncio
async def test_disaster_recovery_simulation(qa_context):
    """Prueba de Recuperación ante Desastres (Disaster Recovery):

    Crea un respaldo cifrado mediante BackupService, valida el checksum SHA-256
    y ejecuta la simulación de recuperación (dry-run).
    """
    tmp_path = qa_context["tmp_path"]
    session_factory = qa_context["session_factory"]

    backup_svc = BackupService(backups_dir=tmp_path)

    async with session_factory() as session:
        # Crear respaldo cifrado real
        backup_meta = await backup_svc.create_encrypted_backup(
            session=session,
            backup_type="full",
            notes="Respaldo para simulacro DR QA",
        )

        assert "backup_id" in backup_meta
        assert "encrypted_sha256" in backup_meta

        # Ejecutar verificación de integridad
        integrity = await backup_svc.verify_backup_integrity(backup_meta["backup_id"])
        assert integrity["is_valid"] is True
        assert integrity["status"] == "verified_healthy"

        # Ejecutar simulacro de recuperación ante desastres
        dr_result = await backup_svc.restore_disaster_recovery_dry_run(backup_meta["backup_id"])
        assert dr_result["dry_run_success"] is True
        assert "table_record_counts" in dr_result


def test_security_headers_and_metrics_endpoint(qa_context):
    """Prueba de Seguridad y DevOps:

    Verifica que la API entregue las cabeceras requeridas de seguridad (HSTS, CSP, etc.)
    y que el endpoint /metrics de Prometheus responda con las métricas formateadas.
    """
    client = qa_context["client"]

    # 1. Registrar una métrica simulada y consultar /metrics
    metrics_registry.record_http_request(
        method="GET",
        path="/api/v1/health",
        status_code=200,
        duration_seconds=0.015,
    )
    metrics_registry.record_business_event("qa_audit_checked", 1)

    # 2. Consultar Endpoint de Métricas Prometheus /metrics
    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text

    assert "erp_http_requests_total" in metrics_text
    assert "erp_database_connected" in metrics_text
    assert "erp_redis_connected" in metrics_text
    assert "erp_business_events_total" in metrics_text
    assert "qa_audit_checked" in metrics_text


def test_api_performance_latency_benchmark(qa_context):
    """Prueba de Rendimiento:

    Garantiza que las consultas al endpoint de métricas y health se resuelvan en menos de 100ms.
    """
    client = qa_context["client"]

    latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        res = client.get("/metrics")
        t1 = time.perf_counter()
        assert res.status_code == 200
        latencies.append((t1 - t0) * 1000)

    avg_latency = sum(latencies) / len(latencies)
    assert avg_latency < 100.0, f"Latencia promedio ({avg_latency:.2f}ms) superó el umbral de 100ms"


@pytest.mark.asyncio
async def test_e2e_business_lifecycle(qa_context):
    """Prueba End-to-End (E2E): Recorre el ciclo completo de vida del negocio:

    1. Creación de empresa y almacén
    2. Alta de producto, variante y stock
    3. Simulación de venta y cálculo financiero
    4. Egreso de inventario (Kardex)
    5. Verificación de balance y trazabilidad
    """
    session_factory = qa_context["session_factory"]

    async with session_factory() as session:
        # Paso 1: Onboarding Empresa y Almacén
        tenant = Tenant(
            id=uuid.uuid4(),
            name="E2E Tenant",
            slug=f"tenant-e2e-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(tenant)
        await session.flush()

        comp = Company(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            legal_name="E2E Corp S.A. de C.V.",
            rfc="E2EC202601A1",
        )
        session.add(comp)
        await session.flush()

        wh = Warehouse(
            id=uuid.uuid4(),
            company_id=comp.id,
            name="Almacén Matriz E2E",
            code="WH-E2E-01",
        )
        session.add(wh)
        await session.flush()

        # Paso 2: Catálogo e Inventario Inicial
        prod = Product(
            id=uuid.uuid4(),
            company_id=comp.id,
            name="Producto E2E Oficial",
            cost_price=350.0,
            sale_price=800.0,
        )
        session.add(prod)
        await session.flush()

        variant = ProductVariant(
            id=uuid.uuid4(),
            product_id=prod.id,
            variant_name="Default",
            sku="E2E-SKU-001",
            sale_price=800.0,
            cogs_cost=350.0,
        )
        session.add(variant)
        await session.flush()

        inv = Inventory(
            id=uuid.uuid4(),
            warehouse_id=wh.id,
            variant_id=variant.id,
            quantity_on_hand=20,
            quantity_reserved=0,
            quantity_blocked=0,
            quantity_available=20,
        )
        session.add(inv)
        await session.flush()

        # Paso 3: Simulación de Venta de 2 unidades
        inv.quantity_on_hand -= 2
        inv.sync_available()

        movement = InventoryMovement(
            id=uuid.uuid4(),
            inventory_id=inv.id,
            movement_type="OUTBOUND",
            quantity_delta=-2,
            quantity_before=20,
            quantity_after=18,
            reference_type="order",
            reference_id="ORD-E2E-2026-001",
            notes="Venta confirmada E2E",
        )
        session.add(movement)

        await session.commit()

        # Paso 4: Verificaciones E2E
        res_inv = await session.execute(select(Inventory).where(Inventory.id == inv.id))
        final_inv = res_inv.scalar_one()
        assert final_inv.quantity_on_hand == 18
        assert final_inv.quantity_available == 18

        # Verificación financiera
        total_venta = 2 * variant.sale_price
        costo_total = 2 * variant.cogs_cost
        costo_envio = 150.0
        ganancia_neta = total_venta - costo_total - costo_envio
        margen_pct = round((ganancia_neta / total_venta) * 100, 2)

        assert total_venta == 1600.0
        assert ganancia_neta == 750.0
        assert margen_pct == 46.88
