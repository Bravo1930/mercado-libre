# Catálogo Oficial de Endpoints - API REST v1

**Sistema:** ERP Inteligente para Mercado Libre México  
**Versión API:** v1.0.0  
**Prefijo Base:** `/api/v1`  
**Protocolo:** HTTPS / JSON  
**Autenticación:** JWT Bearer Token (Usuarios ERP) / Fernet AES-256 (Tokens Meli)

---

## 1. Convenciones Globales y Formatos

### Encabezados Estándar (Request Headers)
| Header | Tipo | Requerido | Descripción |
| :--- | :--- | :--- | :--- |
| `Authorization` | String | Sí (Rutas protegidas) | `Bearer <JWT_TOKEN>` emitido por `/api/v1/users/login` |
| `Content-Type` | String | Sí (`POST`, `PUT`) | `application/json` |
| `X-Request-ID` | String (UUID) | Opcional | Identificador de correlación para trazabilidad distribuida |

### Estructura de Respuesta Paginada (`Page[T]`)
Todos los endpoints de consulta de colecciones implementan paginación uniforme:
```json
{
  "items": [ ... ],
  "total": 154,
  "page": 1,
  "size": 50,
  "pages": 4
}
```
**Parámetros de consulta para paginación:**
- `page` (int, default=1, min=1): Número de página solicitada.
- `size` (int, default=50, min=1, max=100): Cantidad de registros por página.

### Estructura Canónica de Errores
Todos los errores de la API devuelven una carga estructurada con trazabilidad:
```json
{
  "error_code": "ENTITY_NOT_FOUND",
  "message": "Empresa con id '3fa85f64-5717-4562-b3fc-2c963f66afa6' no encontrada.",
  "details": {
    "entity": "Empresa",
    "field": "id",
    "value": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  },
  "timestamp": "2026-11-18T06:12:00.123456Z",
  "request_id": "4a123f8b-1234-5678-9abc-def012345678"
}
```

---

## 2. Monitoreo y Diagnóstico

### `GET /api/v1/health`
Comprueba la disponibilidad operativa de todos los componentes de la infraestructura: base de datos PostgreSQL, cluster Redis, espacio en disco y tiempo de actividad.

- **Autenticación:** Ninguna (Público para orquestadores, Docker y Caddy).
- **Respuesta Exitosa (HTTP 200 OK):**
```json
{
  "status": "healthy",
  "environment": "development",
  "node_name": "erp-node-primary",
  "timestamp": "2026-11-18T06:15:00.000000Z",
  "python_version": "3.13.14",
  "checks": {
    "database": {
      "status": "up",
      "details": "Conexión a PostgreSQL exitosa",
      "host": "localhost:5432",
      "database_name": "erp_meli"
    },
    "redis": {
      "status": "up",
      "details": "Conexión a Redis exitosa",
      "host": "localhost:6379"
    },
    "storage": {
      "status": "up",
      "total_gb": 475.25,
      "free_gb": 128.40
    }
  }
}
```
- **Respuesta Degradada (HTTP 503 en Producción):**
  Devuelve `"status": "degraded"` cuando PostgreSQL o Redis están inaccesibles.

---

## 3. Autenticación, Sesiones y Control de Acceso (RBAC)

### `POST /api/v1/auth/register-tenant`
Onboarding integral de una nueva Organización (Tenant), su Empresa fiscal con RFC y el Usuario Administrador inicial en una sola transacción atómica.

- **Request Body:**
```json
{
  "tenant_name": "Logística y Comercio Global S.A.",
  "tenant_slug": "comercio-global",
  "company_legal_name": "Logística y Comercio Global de México S.A. de C.V.",
  "company_rfc": "LCG190412XYZ",
  "admin_email": "director@comercioglobal.mx",
  "admin_password": "PasswordFuerte2026!",
  "admin_full_name": "Alejandro Morales"
}
```
- **Respuesta (HTTP 201 Created):**
```json
{
  "tenant_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "tenant_name": "Logística y Comercio Global S.A.",
  "tenant_slug": "comercio-global",
  "company_id": "c1a45f64-5717-4562-b3fc-2c963f66afa6",
  "company_legal_name": "Logística y Comercio Global de México S.A. de C.V.",
  "company_rfc": "LCG190412XYZ",
  "user_id": "d1a45f64-5717-4562-b3fc-2c963f66afa6",
  "email": "director@comercioglobal.mx",
  "role": "company_admin",
  "created_at": "2026-11-18T06:15:00Z"
}
```

### `POST /api/v1/auth/login`
Autentica al usuario mediante contraseña con hash bcrypt, genera un identificador de sesión único (`jti`), registra la sesión activa en base de datos y emite el token JWT junto con el listado de empresas autorizadas.

- **Request Body:**
```json
{
  "email": "director@comercioglobal.mx",
  "password": "PasswordFuerte2026!",
  "device_info": "Chrome Windows 11"
}
```
- **Respuesta (HTTP 200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in_minutes": 1440,
  "user": {
    "id": "d1a45f64-5717-4562-b3fc-2c963f66afa6",
    "email": "director@comercioglobal.mx",
    "full_name": "Alejandro Morales",
    "role": "company_admin",
    "is_active": true,
    "is_superuser": false,
    "last_login_at": "2026-11-18T06:20:00Z"
  },
  "authorized_companies": [
    {
      "company_id": "c1a45f64-5717-4562-b3fc-2c963f66afa6",
      "legal_name": "Logística y Comercio Global de México S.A. de C.V.",
      "rfc": "LCG190412XYZ",
      "role": "company_admin",
      "permissions": [],
      "restricted_modules": []
    }
  ]
}
```

### `POST /api/v1/auth/logout`
Cierra la sesión activa actual revocando inmediatamente su identificador (`jti`) en base de datos. Cualquier intento posterior de reutilizar el token JWT será rechazado con HTTP 401.

- **Encabezados:** `Authorization: Bearer <TOKEN>`
- **Respuesta (HTTP 200 OK):**
```json
{
  "status": "success",
  "message": "Sesión finalizada exitosamente."
}
```

### `POST /api/v1/auth/logout-all`
Revoca todas las sesiones activas del usuario en todos sus dispositivos (cierre de sesión global).

- **Encabezados:** `Authorization: Bearer <TOKEN>`
- **Respuesta (HTTP 200 OK):**
```json
{
  "status": "success",
  "message": "Todas las sesiones activas han sido revocadas."
}
```

### `POST /api/v1/auth/forgot-password`
Solicitud de recuperación de contraseña. Genera un token criptográfico de un solo uso con expiración de 1 hora.

- **Request Body:** `{"email": "director@comercioglobal.mx"}`
- **Respuesta (HTTP 200 OK):**
```json
{
  "status": "success",
  "message": "Si el correo electrónico se encuentra registrado, se han generado las instrucciones de recuperación.",
  "reset_token_dev": "dGVzdF90b2tlbl9yZXNldF8yMDI2..."
}
```

### `POST /api/v1/auth/reset-password`
Restablece la contraseña del usuario utilizando el token criptográfico recibido. Invalida el token tras el uso y revoca automáticamente todas las sesiones previas del usuario por seguridad.

- **Request Body:**
```json
{
  "token": "dGVzdF90b2tlbl9yZXNldF8yMDI2...",
  "new_password": "NuevaPasswordSegura2026#"
}
```
- **Respuesta (HTTP 200 OK):**
```json
{
  "status": "success",
  "message": "Contraseña actualizada exitosamente. Todas las sesiones activas han sido cerradas por seguridad."
}
```

### `GET /api/v1/auth/me`
Retorna el perfil del usuario autenticado actualmente.

### `GET /api/v1/auth/my-companies`
Retorna la lista de todas las empresas a las que el usuario tiene acceso operativo, con su rol específico en cada una.

### `GET /api/v1/auth/sessions`
Lista las sesiones registradas del usuario con dirección IP, navegador, fecha de última actividad y bandera `is_current`.

### `DELETE /api/v1/auth/sessions/{session_id}`
Revoca una sesión específica para cerrar el acceso en un dispositivo particular.

---

## 3.1 Matriz de Roles y Control de Acceso

El ERP implementa **8 roles oficiales**:

| # | Rol | Identificador | Alcance | Descripción de Privilegios |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Propietario de plataforma | `platform_owner` | Global SaaS | Máxima autoridad de la plataforma, tenants y métricas globales. **No accede a documentos privados sin membresía.** |
| 2 | Administrador SaaS | `saas_admin` | Global SaaS | Gestión de tenants, suscripciones y soporte técnico. **Sin acceso irrestricto a documentos privados.** |
| 3 | Administrador de empresa | `company_admin` | Empresa | Control total operativo, fiscal, catálogo, usuarios, almacenes y finanzas de su empresa. |
| 4 | Director | `director` | Empresa | Visualización integral de ventas, catálogo, auditoría y KPIs financieros. No altera configuraciones del sistema. |
| 5 | Operador | `operator` | Empresa | Operaciones de catálogo, actualización de pedidos y logística. **Bloqueado de Finanzas, Auditoría y Configuración.** |
| 6 | Responsable de almacén | `warehouse_manager` | Empresa | Gestión de almacenes, existencias, ajustes Kardex y recepción. **Bloqueado de Finanzas y Credenciales MeLi.** |
| 7 | Responsable financiero | `financial_manager` | Empresa | Análisis de rentabilidad SAT, COGS, retenciones y compras. **Bloqueado de ajustes físicos de inventario.** |
| 8 | Usuario de consulta | `viewer` | Empresa | Acceso de solo lectura a catálogo y dashboards básicos. **Sin permisos de modificación ni acceso financiero.** |

---

## 3.2 Administración de Usuarios Multi-Empresa

### `POST /api/v1/companies/{company_id}/users`
Asigna o vincula a un usuario existente dentro de la empresa activa, especificando su rol local, permisos adicionales y módulos restringidos.

- **Permiso requerido:** `companies:manage`
- **Request Body:**
```json
{
  "user_id": "e1f7a245-8a8b-4a62-9e23-74d12c8e3120",
  "role": "operator",
  "permissions": ["catalog:create", "catalog:update"],
  "restricted_modules": ["finance", "settings"]
}
```
- **Respuesta (HTTP 201 Created):** Retorna `CompanyUserResponse`.
- **Prevención de Escalamiento:** El backend valida que el solicitante no pueda otorgar un rol superior al suyo (`can_assign_role`).

### `GET /api/v1/companies/{company_id}/users`
Lista todos los usuarios con acceso asignado a la empresa.

### `PUT /api/v1/companies/{company_id}/users/{target_user_id}`
Actualiza el rol, permisos o módulos restringidos de un miembro de la empresa.

### `DELETE /api/v1/companies/{company_id}/users/{target_user_id}`
Revoca el acceso del usuario a la empresa. Impide que el último administrador se auto-elimine.

---

## 3.3 Reglas Estrictas de Seguridad

1. **Aislamiento Multi-Empresa Estricto:** Cada consulta y mutación en la base de datos se filtra obligatoriamente por el `company_id` verificado en backend (`CompanyContext`).
2. **Cero Confianza en el Frontend (Zero Trust):** Los identificadores enviados en encabezados (`X-Company-ID`), parámetros de consulta (`company_id`) o cuerpos JSON se verifican en la base de datos contra los registros activos de `CompanyUser`. Cualquier intento de acceso a una empresa no asignada resulta en `HTTP 403 Forbidden`.
3. **Protección de Documentos Privados:** Los administradores globales (`platform_owner`, `saas_admin`) no tienen acceso irrestricto a módulos privados (`finance`, `orders`, `meli_accounts`, `settings`) a menos que cuenten con una asignación explícita como miembros de la empresa.
4. **Prevención de Escalamiento de Privilegios:** La jerarquía de roles se valida estrictamente en el backend. Un operador o responsable de almacén no puede crear empresas ni otorgar permisos administrativos.

### `POST /api/v1/users`
Registra un nuevo usuario dentro de la organización. Requiere rol `admin`. La contraseña se almacena con hash `bcrypt`.

- **Request Body:**
```json
{
  "tenant_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "email": "operador@empresa.com.mx",
  "password": "ClaveSegura2026#",
  "full_name": "Ana Gómez",
  "role": "operator"
}
```
- **Respuesta (HTTP 201 Created):** Retorna `UserResponse` (sin campo de contraseña).
- **Errores:** `409 Conflict` (El email ya se encuentra registrado).

---

## 4. Flujo OAuth 2.0 con Mercado Libre México

### `GET /api/v1/auth/meli/authorize-url`
Genera la URL oficial de autorización del portal de Mercado Libre México (`auth.mercadolibre.com.mx/authorization`) con el `company_id` codificado en el parámetro `state`.

- **Query Params:**
  - `company_id` (UUID, requerido): Identificador de la empresa a vincular.
- **Respuesta (HTTP 200 OK):**
```json
{
  "authorization_url": "https://auth.mercadolibre.com.mx/authorization?response_type=code&client_id=1234567890&redirect_uri=https%3A%2F%2Ferp.tudominio.com%2Fapi%2Fv1%2Fauth%2Fmeli%2Fcallback&state=b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "site_id": "MLM",
  "redirect_uri": "https://erp.tudominio.com/api/v1/auth/meli/callback"
}
```

### `GET /api/v1/auth/meli/callback`
Callback oficial registrado en la consola de Mercado Libre Developers. Recibe el código temporal (`code`), lo canjea contra el endpoint `/oauth/token` de MeLi, encripta los tokens con AES-256 y persiste la cuenta.

- **Query Params:**
  - `code` (string, requerido): Authorization code emitido por Mercado Libre.
  - `state` (UUID, requerido): `company_id` de la empresa vinculante.
- **Respuesta (HTTP 200 OK):**
```json
{
  "status": "success",
  "message": "Cuenta de Mercado Libre vinculada exitosamente",
  "account": {
    "id": "e9b7a245-8a8b-4a62-9e23-74d12c8e3120",
    "meli_user_id": 987654321,
    "nickname": "TIENDA_OFICIAL_MEX",
    "site_id": "MLM",
    "company_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
    "is_active": true,
    "token_expires_at": "2026-11-18T12:00:00Z"
  }
}
```

---

## 5. Gestión Multi-Empresa (RFC Mexicano)

### `POST /api/v1/companies`
Registra una razón social o empresa fiscal mexicana con validación estricta de RFC oficial (Persona Física de 13 dígitos o Persona Moral de 12 dígitos con homoclave).

- **Request Body:**
```json
{
  "tenant_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "legal_name": "Distribuidora Comercial de México S.A. de C.V.",
  "rfc": "DCM010101ABC",
  "fiscal_regime": "601",
  "email": "contacto@distribuidoramex.com",
  "phone": "+52 55 5555 1234"
}
```
- **Respuesta (HTTP 201 Created):** Retorna `CompanyResponse`.
- **Errores:**
  - `422 Unprocessable Entity`: Formato de RFC inválido.
  - `409 Conflict`: Ya existe una empresa con ese RFC dentro del mismo tenant.

### `GET /api/v1/companies`
Lista empresas con paginación y filtros opcionales.

- **Query Params:**
  - `tenant_id` (UUID, opcional): Filtrar por organización.
  - `is_active` (bool, opcional): Filtrar por estatus.
  - `page` (int, default=1), `size` (int, default=50).
- **Respuesta (HTTP 200 OK):** `Page[CompanyResponse]`.

### `GET /api/v1/companies/{id}`
Obtiene el detalle de una empresa por su UUID.
- **Errores:** `404 Not Found`.

---

## 6. Cuentas de Mercado Libre México

### `POST /api/v1/meli-accounts`
Registra o vincula directamente una cuenta de Mercado Libre con cifrado de tokens en reposo.

- **Request Body:**
```json
{
  "company_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "meli_user_id": 123456789,
  "nickname": "MERCADOLIBRE_OFICIAL_MX",
  "access_token_plain": "APP_USR-1234567890-abcdef...",
  "refresh_token_plain": "TG-1234567890-abcdef...",
  "expires_in_seconds": 21600
}
```
- **Respuesta (HTTP 201 Created):** Retorna `MeliAccountResponse` (los tokens nunca son expuestos en texto plano).
- **Errores:** `409 Conflict` (El `meli_user_id` ya está vinculado).

### `GET /api/v1/meli-accounts`
Lista las cuentas de Mercado Libre vinculadas a una empresa.
- **Query Params:**
  - `company_id` (UUID, requerido).
  - `page`, `size`.

---

## 7. Catálogo de Productos Maestros, Variantes y SKUs

### `POST /api/v1/products`
Crea de forma transaccional un producto maestro y sus variantes iniciales con código de barras EAN-13 y costo de adquisición (COGS).

- **Request Body:**
```json
{
  "company_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Termo Inteligente de Acero Inoxidable 500ml",
  "brand": "ThermoTech",
  "category": "Hogar y Cocina",
  "description": "Termo con pantalla táctil LED indicadora de temperatura.",
  "variants": [
    {
      "variant_name": "Negro Mate / 500ml",
      "sku": "TT-500-BLK",
      "barcode_ean": "7501234567890",
      "cogs_cost": 120.50
    },
    {
      "variant_name": "Plata Acero / 500ml",
      "sku": "TT-500-SLV",
      "barcode_ean": "7501234567891",
      "cogs_cost": 115.00
    }
  ]
}
```
- **Respuesta (HTTP 201 Created):** Retorna `ProductResponse` con el array anidado de `variants`.

### `GET /api/v1/products`
Búsqueda y consulta paginada del catálogo de productos.
- **Query Params:**
  - `company_id` (UUID, requerido).
  - `search` (string, opcional): Búsqueda por coincidencia en nombre o marca.
  - `page`, `size`.

### `POST /api/v1/products/skus`
Mapea un SKU del ERP a una publicación o variación activa en Mercado Libre México (`MLM...`).

- **Request Body:**
```json
{
  "meli_account_id": "e9b7a245-8a8b-4a62-9e23-74d12c8e3120",
  "variant_id": "8a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "meli_item_id": "MLM1987654321",
  "meli_variation_id": 17892348921,
  "seller_sku": "TT-500-BLK",
  "sync_stock": true,
  "sync_price": true
}
```
- **Respuesta (HTTP 201 Created):** Retorna `ProductSKUResponse`.

---

## 8. Almacenes & Centros Logísticos

### `POST /api/v1/warehouses`
Registra una ubicación de inventario (Almacén Central, Bodega Física, Bodega Mercado Libre Full `FULL_MLM`, etc.).

- **Request Body:**
```json
{
  "company_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Centro de Distribución CDMX",
  "code": "CEDIS-CDMX",
  "warehouse_type": "physical",
  "address": "Av. Insurgentes Sur 1602, Benito Juárez, CDMX",
  "is_active": true
}
```
- **Respuesta (HTTP 201 Created):** `WarehouseResponse`.

### `GET /api/v1/warehouses`
Lista todos los almacenes de una empresa.
- **Query Params:** `company_id` (UUID, requerido).

---

## 9. Inventario & Kardex Transaccional con Bloqueo Pesimista

### `POST /api/v1/inventory/adjust`
Ejecuta un ajuste o movimiento de inventario de forma estrictamente transaccional. Aplica `SELECT ... FOR UPDATE` sobre la fila del inventario, valida que el saldo no resulte negativo y registra el movimiento de auditoría en el Kardex.

- **Request Body:**
```json
{
  "warehouse_id": "f1e2d3c4-b5a6-7890-1234-567890abcdef",
  "variant_id": "8a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "quantity_delta": 50,
  "movement_type": "PURCHASE",
  "notes": "Recepción de compra OC-2026-001"
}
```
- **Respuesta (HTTP 200 OK):**
```json
{
  "id": "7b8c9d0e-1f2a-3b4c-5d6e-7f8a9b0c1d2e",
  "warehouse_id": "f1e2d3c4-b5a6-7890-1234-567890abcdef",
  "variant_id": "8a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
  "quantity_available": 150,
  "quantity_reserved": 10,
  "quantity_total": 160,
  "updated_at": "2026-11-18T06:18:22Z"
}
```
- **Errores:**
  - `400 Bad Request` (`INSUFFICIENT_STOCK`): El ajuste dejaría el stock en saldo negativo.
  - `404 Not Found`: Variante o almacén no localizados.

### `GET /api/v1/inventory`
Consulta existencias globales o filtradas por almacén o producto.
- **Query Params:**
  - `warehouse_id` (UUID, opcional).
  - `variant_id` (UUID, opcional).
  - `page`, `size`.

### `GET /api/v1/inventory/movements`
Consulta el historial cronológico (Kardex) de auditoría de movimientos de stock.
- **Query Params:**
  - `inventory_id` (UUID, opcional).
  - `movement_type` (string, opcional): `PURCHASE`, `SALE`, `ADJUSTMENT`, `RETURN`, `TRANSFER`.
  - `page`, `size`.

---

## 10. Ventas, Pedidos y Auditoría de Utilidad SAT

### `GET /api/v1/orders`
Consulta pedidos y ventas de Mercado Libre con paginación, filtros avanzados y relaciones precargadas (`items`, `payments`, `shipments`, `profitability`).

- **Query Params:**
  - `meli_account_id` (UUID, opcional).
  - `status` (string, opcional): `paid`, `cancelled`, `pending`.
  - `date_from` (ISO Datetime, opcional): Fecha de inicio de búsqueda.
  - `date_to` (ISO Datetime, opcional): Fecha de término de búsqueda.
  - `page`, `size`.
- **Respuesta (HTTP 200 OK):** `Page[OrderResponse]` con desglose financiero:
```json
{
  "items": [
    {
      "id": "3e4f5a6b-7c8d-9e0f-1a2b-3c4d5e6f7a8b",
      "meli_account_id": "e9b7a245-8a8b-4a62-9e23-74d12c8e3120",
      "meli_order_id": 2000000001,
      "status": "paid",
      "total_amount": 899.00,
      "paid_amount": 899.00,
      "date_created_meli": "2026-11-18T05:00:00Z",
      "items": [
        {
          "meli_item_id": "MLM1987654321",
          "title": "Termo Inteligente Acero 500ml",
          "quantity": 2,
          "unit_price": 449.50,
          "sale_fee": 116.87
        }
      ],
      "payments": [
        {
          "meli_payment_id": 5000000001,
          "status": "approved",
          "total_paid_amount": 899.00,
          "net_received_amount": 782.13
        }
      ],
      "shipments": [
        {
          "meli_shipment_id": 4000000001,
          "logistic_type": "fulfillment",
          "status": "delivered",
          "tracking_number": "MLM-TRACK-998877"
        }
      ],
      "profitability": {
        "gross_sale_price": 899.00,
        "cogs_total": 241.00,
        "meli_commission_fee": 116.87,
        "shipping_cost_seller": 0.00,
        "sat_iva_retention": 71.92,
        "sat_isr_retention": 8.99,
        "net_profit": 460.22,
        "net_margin_percentage": 51.19
      }
    }
  ],
  "total": 1,
  "page": 1,
  "size": 50,
  "pages": 1
}
```

### `GET /api/v1/orders/{order_id}`
Obtiene el detalle completo de una orden por su UUID interno.

---

## 11. Proveedores y Órdenes de Compra

### `POST /api/v1/suppliers`
Registra un nuevo proveedor de mercancía para la empresa.

- **Request Body:**
```json
{
  "company_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Comercializadora Mayorista de Oriente S.A.",
  "rfc": "CMO980715XY1",
  "contact_name": "Ing. Roberto Peña",
  "email": "ventas@cmo.com.mx",
  "phone": "+52 55 1234 5678",
  "lead_time_days": 7
}
```
- **Respuesta (HTTP 201 Created):** `SupplierResponse`.

### `POST /api/v1/suppliers/purchase-orders`
Crea una orden de compra con sus partidas detalladas en una sola transacción atómica, calculando el importe total automáticamente.

- **Request Body:**
```json
{
  "company_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "supplier_id": "d1c2b3a4-5678-90ab-cdef-1234567890ab",
  "order_number": "OC-2026-001",
  "notes": "Abastecimiento inicial Q1",
  "items": [
    {
      "variant_id": "8a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
      "quantity_ordered": 200,
      "unit_cost": 115.00
    }
  ]
}
```
- **Respuesta (HTTP 201 Created):** `PurchaseOrderResponse`.

---

## 12. Configuraciones de Empresa

### `POST /api/v1/settings`
Guarda o actualiza una configuración clave-valor estructurada para la empresa (Upsert idempotente).

- **Request Body:**
```json
{
  "company_id": "b1a45f64-5717-4562-b3fc-2c963f66afa6",
  "key": "sync_stock_safety_margin",
  "value": {
    "safety_buffer": 2,
    "pause_under": 1,
    "notify_email": "alertas@empresa.com.mx"
  },
  "description": "Margen de seguridad para no vender inventario inexistente en Mercado Libre"
}
```
- **Respuesta (HTTP 200 OK):** `CompanySettingResponse`.

### `GET /api/v1/settings`
Lista las configuraciones activas de una empresa.
- **Query Params:** `company_id` (UUID, requerido).

---

## 13. Pistas de Auditoría y Trazabilidad

### `GET /api/v1/audit`
Consulta el registro inmutable de auditoría para trazabilidad y cumplimiento legal/fiscal.

- **Query Params:**
  - `company_id` (UUID, requerido).
  - `action` (string, opcional): Filtrar por acción (`CREATE`, `UPDATE`, `DELETE`, `STOCK_ADJUSTMENT`, etc.).
  - `entity_name` (string, opcional): Filtrar por entidad (`Product`, `Company`, `Inventory`, etc.).
  - `page`, `size`.
- **Respuesta (HTTP 200 OK):** `Page[AuditLogResponse]`.

---

## 14. Ingesta de Webhooks de Mercado Libre en Tiempo Real

### `POST /api/v1/webhooks/meli`
Punto de entrada oficial para notificaciones push en tiempo real de Mercado Libre México (tópicos: `orders_v2`, `items`, `shipments`, `payments`, etc.).

- **Requisitos de Mercado Libre:**
  - **SLA de Respuesta:** **Menos de 500 ms** con código HTTP 200.
  - **Estrategia Implementada:** Encolamiento inmediato no bloqueante en Redis (`RPUSH meli_webhooks_queue`). Procesamiento en segundo plano por workers de Celery/RQ para evitar timeouts y la consecuente baja del webhook por MeLi.
- **Request Body (Emitido por Mercado Libre):**
```json
{
  "resource": "/orders/2000000001",
  "user_id": 987654321,
  "topic": "orders_v2",
  "application_id": 1234567890,
  "attempts": 1,
  "sent": "2026-11-18T06:12:00.123Z"
}
```
- **Respuesta Inmediata (HTTP 200 OK):**
```json
{
  "status": "received",
  "queue_position": 1,
  "topic": "orders_v2"
}
```
