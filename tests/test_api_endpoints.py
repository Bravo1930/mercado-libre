"""Pruebas de validación de datos, esquemas Pydantic, excepciones y paginación."""

import uuid
import pytest
from pydantic import ValidationError

from src.core.exceptions import (
    AppException,
    BusinessRuleViolationException,
    EntityAlreadyExistsException,
    EntityNotFoundException,
    InsufficientStockException,
)
from src.core.pagination import Page, PaginationParams
from src.core.security import create_access_token, decode_access_token
from src.schemas.common import RFC_REGEX
from src.schemas.product import ProductCreate, ProductVariantCreate
from src.schemas.tenant import CompanyCreate
from src.schemas.user import UserCreate


def test_mexican_rfc_regex_validation():
    """Valida exhaustivamente el regex oficial del SAT para RFCs válidos e inválidos."""
    # Válidos (Personas Morales: 12 caracteres, Personas Físicas: 13 caracteres)
    valid_rfcs = [
        "CAN180512AB3",  # PM
        "DMN150820KL4",  # PM
        "GARM850101XYZ",  # PF
        "XAXX010101000",  # Genérico Nacional
        "XEXX010101000",  # Genérico Extranjero
    ]
    for rfc in valid_rfcs:
        assert RFC_REGEX.match(rfc) is not None, f"El RFC válido '{rfc}' falló en el validador."

    # Inválidos
    invalid_rfcs = [
        "RFC_CORTO",
        "123456789012",
        "CAN180512AB",     # Solo 11 caracteres
        "CAN180512AB345",  # Más de 13 caracteres
        "RFC CON ESPACIOS",
    ]
    for rfc in invalid_rfcs:
        assert RFC_REGEX.match(rfc) is None, f"El RFC inválido '{rfc}' fue erróneamente aceptado."


def test_pydantic_company_schema_rfc_validator():
    """Verifica que el schema CompanyCreate rechace RFCs inválidos con ValidationError."""
    tenant_id = uuid.uuid4()

    # Válido
    company_in = CompanyCreate(
        tenant_id=tenant_id,
        legal_name="Comercializadora Válida S.A.",
        rfc="CAN180512AB3",
    )
    assert company_in.rfc == "CAN180512AB3"

    # Inválido
    with pytest.raises(ValidationError) as exc_info:
        CompanyCreate(
            tenant_id=tenant_id,
            legal_name="Empresa Inválida",
            rfc="RFC_INVALIDO_MAL",
        )
    assert "formato oficial del SAT" in str(exc_info.value)


def test_product_schema_validation():
    """Verifica la validación anidada del catálogo de productos y variantes."""
    company_id = uuid.uuid4()

    prod_in = ProductCreate(
        company_id=company_id,
        name="Cable USB-C Reforzado",
        brand="HyperCharge",
        category="Cables",
        variants=[
            ProductVariantCreate(variant_name="1 Metro", sku="CBL-USBC-1M", cogs_cost=25.50),
            ProductVariantCreate(variant_name="2 Metros", sku="CBL-USBC-2M", cogs_cost=35.00),
        ],
    )
    assert len(prod_in.variants) == 2
    assert prod_in.variants[0].sku == "CBL-USBC-1M"
    assert prod_in.variants[0].cogs_cost == 25.50

    # Rechazar variantes con costos negativos
    with pytest.raises(ValidationError):
        ProductVariantCreate(variant_name="Negativo", sku="NEG", cogs_cost=-10.0)


def test_centralized_exceptions_formatting():
    """Verifica la coherencia de las excepciones de dominio para el middleware central."""
    # 404 Not Found
    ex_404 = EntityNotFoundException("Producto", "UUID-123")
    assert ex_404.status_code == 404
    assert ex_404.code == "RESOURCE_NOT_FOUND"
    assert "UUID-123" in ex_404.message

    # 409 Conflict
    ex_409 = EntityAlreadyExistsException("Empresa", "RFC", "CAN180512AB3")
    assert ex_409.status_code == 409
    assert ex_409.code == "RESOURCE_ALREADY_EXISTS"

    # Insufficient Stock
    ex_stock = InsufficientStockException(sku="TEST-SKU", requested=10, available=2)
    assert ex_stock.status_code == 422
    assert ex_stock.code == "BUSINESS_RULE_VIOLATION"
    assert ex_stock.details["sku"] == "TEST-SKU"


def test_pagination_page_calculation():
    """Verifica el cálculo matemático de páginas, flags has_next y has_prev."""
    params = PaginationParams(page=1, page_size=20)
    items = list(range(20))
    page = Page.create(items=items, total_items=45, params=params)

    assert page.total_items == 45
    assert page.total_pages == 3
    assert page.page == 1
    assert page.has_next is True
    assert page.has_prev is False

    # Página 3 (última)
    params_p3 = PaginationParams(page=3, page_size=20)
    page_3 = Page.create(items=list(range(5)), total_items=45, params=params_p3)
    assert page_3.has_next is False
    assert page_3.has_prev is True


def test_jwt_session_token_claims():
    """Verifica que el JWT incluya y decodifique todos los claims del usuario y tenant."""
    claims = {
        "sub": "user-uuid-999",
        "email": "director@empresa.com",
        "role": "admin",
        "tenant_id": "tenant-uuid-111",
    }
    token = create_access_token(claims)
    decoded = decode_access_token(token)

    assert decoded is not None
    assert decoded["sub"] == "user-uuid-999"
    assert decoded["role"] == "admin"
    assert decoded["tenant_id"] == "tenant-uuid-111"
