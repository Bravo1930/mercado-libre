"""Exportación centralizada de esquemas Pydantic v2."""

from src.schemas.common import ApiResponse, BaseSchema
from src.schemas.meli_account import MeliAccountCreate, MeliAccountResponse
from src.schemas.order import (
    OrderItemResponse,
    OrderResponse,
    PaymentResponse,
    ProfitabilityAuditResponse,
    ShipmentResponse,
)
from src.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductSKUCreate,
    ProductSKUResponse,
    ProductVariantCreate,
    ProductVariantResponse,
)
from src.schemas.supplier import (
    AuditLogResponse,
    CompanySettingCreate,
    CompanySettingResponse,
    CostStructureCreate,
    CostStructureResponse,
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    SupplierCreate,
    SupplierResponse,
)
from src.schemas.tenant import (
    CompanyCreate,
    CompanyResponse,
    CompanyUpdate,
    TenantCreate,
    TenantResponse,
)
from src.schemas.user import TokenResponse, UserCreate, UserLogin, UserResponse
from src.schemas.warehouse import (
    InventoryAdjustRequest,
    InventoryMovementResponse,
    InventoryResponse,
    WarehouseCreate,
    WarehouseResponse,
)

__all__ = [
    "BaseSchema",
    "ApiResponse",
    "TenantCreate",
    "TenantResponse",
    "CompanyCreate",
    "CompanyUpdate",
    "CompanyResponse",
    "UserCreate",
    "UserLogin",
    "TokenResponse",
    "UserResponse",
    "MeliAccountCreate",
    "MeliAccountResponse",
    "ProductCreate",
    "ProductResponse",
    "ProductVariantCreate",
    "ProductVariantResponse",
    "ProductSKUCreate",
    "ProductSKUResponse",
    "WarehouseCreate",
    "WarehouseResponse",
    "InventoryAdjustRequest",
    "InventoryResponse",
    "InventoryMovementResponse",
    "OrderResponse",
    "OrderItemResponse",
    "PaymentResponse",
    "ShipmentResponse",
    "ProfitabilityAuditResponse",
    "SupplierCreate",
    "SupplierResponse",
    "PurchaseOrderCreate",
    "PurchaseOrderResponse",
    "CostStructureCreate",
    "CostStructureResponse",
    "CompanySettingCreate",
    "CompanySettingResponse",
    "AuditLogResponse",
]
