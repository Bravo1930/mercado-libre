"""Matriz de Roles, Permisos Granulares y Restricciones Modulares del ERP."""

from enum import Enum


class RoleEnum(str, Enum):
    """Los 8 roles oficiales del sistema ERP multi-empresa."""

    PLATFORM_OWNER = "platform_owner"
    SAAS_ADMIN = "saas_admin"
    COMPANY_ADMIN = "company_admin"
    DIRECTOR = "director"
    OPERATOR = "operator"
    WAREHOUSE_MANAGER = "warehouse_manager"
    FINANCIAL_MANAGER = "financial_manager"
    VIEWER = "viewer"


class ModuleEnum(str, Enum):
    """Módulos funcionales del ERP sujetos a control de acceso."""

    PLATFORM = "platform"
    TENANTS = "tenants"
    COMPANIES = "companies"
    USERS = "users"
    MELI_ACCOUNTS = "meli_accounts"
    CATALOG = "catalog"
    INVENTORY = "inventory"
    ORDERS = "orders"
    LOGISTICS = "logistics"
    FINANCE = "finance"
    COMMERCIAL = "commercial"
    SUPPLIERS = "suppliers"
    SETTINGS = "settings"
    AUDIT = "audit"


class ActionEnum(str, Enum):
    """Acciones operativas sobre los módulos."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MANAGE = "manage"
    EXPORT = "export"
    PRINT_LABEL = "print_label"


# Módulos privados y confidenciales que requieren pertenencia explícita a la empresa
# Los administradores globales (platform_owner / saas_admin) NO tienen acceso irrestricto a ellos sin asignación.
PRIVATE_COMPANY_MODULES: set[str] = {
    ModuleEnum.FINANCE.value,
    ModuleEnum.ORDERS.value,
    ModuleEnum.MELI_ACCOUNTS.value,
    ModuleEnum.SETTINGS.value,
    ModuleEnum.INVENTORY.value,
    ModuleEnum.COMMERCIAL.value,
}

# Matriz base de permisos por defecto para cada rol
ROLE_DEFAULT_PERMISSIONS: dict[str, set[str]] = {
    RoleEnum.PLATFORM_OWNER.value: {
        "platform:manage_tenants",
        "platform:view_metrics",
        "tenants:create",
        "tenants:read",
        "tenants:update",
        "tenants:delete",
        "companies:create",
        "companies:read",
    },
    RoleEnum.SAAS_ADMIN.value: {
        "platform:manage_tenants",
        "platform:view_metrics",
        "tenants:create",
        "tenants:read",
        "tenants:update",
        "companies:create",
        "companies:read",
    },
    RoleEnum.COMPANY_ADMIN.value: {
        "companies:read",
        "companies:update",
        "companies:manage_users",
        "users:read",
        "users:create",
        "users:update",
        "users:delete",
        "users:manage_roles",
        "meli_accounts:read",
        "meli_accounts:create",
        "meli_accounts:update",
        "meli_accounts:delete",
        "meli_accounts:manage",
        "meli_accounts:link",
        "meli_accounts:unlink",
        "meli_accounts:refresh",
        "catalog:read",
        "catalog:create",
        "catalog:update",
        "catalog:delete",
        "catalog:manage",
        "inventory:read",
        "inventory:create",
        "inventory:update",
        "inventory:delete",
        "inventory:manage",
        "inventory:adjust",
        "inventory:transfer",
        "inventory:count",
        "inventory:alerts",
        "inventory:manage_warehouses",
        "inventory:kardex",
        "orders:read",
        "orders:update",
        "orders:cancel",
        "orders:manage",
        "logistics:read",
        "logistics:print_label",
        "logistics:update",
        "commercial:read",
        "commercial:create",
        "commercial:update",
        "commercial:delete",
        "commercial:manage",
        "finance:read",
        "finance:create",
        "finance:update",
        "finance:export",
        "finance:manage_cogs",
        "finance:audit_sat",
        "suppliers:read",
        "suppliers:create",
        "suppliers:update",
        "suppliers:delete",
        "suppliers:purchase_orders",
        "settings:read",
        "settings:update",
        "audit:read",
    },
    RoleEnum.DIRECTOR.value: {
        "companies:read",
        "users:read",
        "meli_accounts:read",
        "meli_accounts:create",
        "meli_accounts:update",
        "catalog:read",
        "catalog:create",
        "catalog:update",
        "inventory:read",
        "inventory:adjust",
        "inventory:transfer",
        "inventory:count",
        "inventory:alerts",
        "inventory:kardex",
        "orders:read",
        "orders:update",
        "logistics:read",
        "commercial:read",
        "commercial:create",
        "commercial:update",
        "finance:read",
        "finance:export",
        "suppliers:read",
        "suppliers:purchase_orders",
        "audit:read",
    },
    RoleEnum.OPERATOR.value: {
        "companies:read",
        "catalog:read",
        "catalog:create",
        "catalog:update",
        "inventory:read",
        "inventory:adjust",
        "inventory:transfer",
        "inventory:count",
        "orders:read",
        "orders:update",
        "logistics:read",
        "logistics:print_label",
        "logistics:update",
        "suppliers:read",
    },
    RoleEnum.WAREHOUSE_MANAGER.value: {
        "companies:read",
        "catalog:read",
        "inventory:read",
        "inventory:create",
        "inventory:update",
        "inventory:delete",
        "inventory:manage",
        "inventory:adjust",
        "inventory:transfer",
        "inventory:count",
        "inventory:alerts",
        "inventory:manage_warehouses",
        "inventory:kardex",
        "logistics:read",
        "logistics:print_label",
        "logistics:update",
        "suppliers:read",
        "suppliers:purchase_orders",
    },
    RoleEnum.FINANCIAL_MANAGER.value: {
        "companies:read",
        "catalog:read",
        "orders:read",
        "commercial:read",
        "commercial:update",
        "finance:read",
        "finance:create",
        "finance:update",
        "finance:export",
        "finance:manage_cogs",
        "finance:audit_sat",
        "suppliers:read",
        "suppliers:purchase_orders",
    },
    RoleEnum.VIEWER.value: {
        "companies:read",
        "catalog:read",
        "inventory:read",
        "orders:read",
        "logistics:read",
        "suppliers:read",
    },
}

# Jerarquía para validación de escalamiento de privilegios
ROLE_HIERARCHY_LEVEL: dict[str, int] = {
    RoleEnum.PLATFORM_OWNER.value: 100,
    RoleEnum.SAAS_ADMIN.value: 80,
    RoleEnum.COMPANY_ADMIN.value: 60,
    RoleEnum.DIRECTOR.value: 50,
    RoleEnum.FINANCIAL_MANAGER.value: 40,
    RoleEnum.WAREHOUSE_MANAGER.value: 30,
    RoleEnum.OPERATOR.value: 20,
    RoleEnum.VIEWER.value: 10,
}


def has_module_permission(
    role: str,
    module: str,
    action: str,
    custom_permissions: list[str] | None = None,
    restricted_modules: list[str] | None = None,
) -> bool:
    """
    Evalúa si un usuario posee autorización para ejecutar una acción sobre un módulo.
    Aplica regla de precedencia:
    1. Si el módulo está explícitamente restringido -> Denegado.
    2. Si existe un permiso personalizado positivo -> Concedido.
    3. Si el rol por defecto incluye el permiso o el comodín 'manage' -> Concedido.
    4. De lo contrario -> Denegado.
    """
    if restricted_modules and module in restricted_modules:
        return False

    perm_key = f"{module}:{action}"
    manage_key = f"{module}:manage"

    if custom_permissions:
        if perm_key in custom_permissions or manage_key in custom_permissions:
            return True

    role_perms = ROLE_DEFAULT_PERMISSIONS.get(role, set())
    return perm_key in role_perms or manage_key in role_perms


def can_assign_role(caller_role: str, target_role: str) -> bool:
    """
    Garantiza que ningún usuario pueda escalar privilegios asignando roles superiores
    o iguales a los suyos, o asignando roles fuera de su jurisdicción.
    """
    caller_level = ROLE_HIERARCHY_LEVEL.get(caller_role, 0)
    target_level = ROLE_HIERARCHY_LEVEL.get(target_role, 0)

    # Solo platform_owner puede asignar platform_owner o saas_admin
    if target_role in {RoleEnum.PLATFORM_OWNER.value, RoleEnum.SAAS_ADMIN.value}:
        return caller_role == RoleEnum.PLATFORM_OWNER.value

    # Para roles de empresa, el que asigna debe ser al menos company_admin
    if caller_level < ROLE_HIERARCHY_LEVEL[RoleEnum.COMPANY_ADMIN.value]:
        return False

    # No se puede asignar un rol de nivel superior al propio
    return caller_level >= target_level
