# Guía Técnica de Integración: API Oficial de Mercado Libre México

## 1. Parámetros Base
- **Base URL:** `https://api.mercadolibre.com`
- **Auth URL:** `https://auth.mercadolibre.com.mx/authorization`
- **Site ID:** `MLM` (México)
- **Moneda:** `MXN` (Pesos Mexicanos)
- **Timezone:** `America/Mexico_City`

---

## 2. Autenticación OAuth 2.0 y Rotación de Refresh Tokens

### Obtención del Código de Autorización
El usuario es redirigido a:
```
https://auth.mercadolibre.com.mx/authorization?response_type=code&client_id={APP_ID}&redirect_uri={REDIRECT_URI}&state={COMPANY_ID}
```

### Canje de Código por Tokens
`POST https://api.mercadolibre.com/oauth/token`
```json
{
  "grant_type": "authorization_code",
  "client_id": "{APP_ID}",
  "client_secret": "{CLIENT_SECRET}",
  "code": "{AUTHORIZATION_CODE}",
  "redirect_uri": "{REDIRECT_URI}"
}
```
**Respuesta:**
```json
{
  "access_token": "APP_USR-...",
  "token_type": "bearer",
  "expires_in": 21600,
  "scope": "offline_access read write",
  "user_id": 123456789,
  "refresh_token": "TG-..."
}
```

### Regla Crítica de Rotación (Single-Use Refresh Token)
- El `access_token` expira cada **6 horas** (21,600 segundos).
- Al usar el `refresh_token` para renovar el acceso, **Mercado Libre emite un nuevo `refresh_token` y destruye el anterior**.
- El ERP utiliza un bloqueo distribuido en Redis (`acquire_distributed_lock("meli_token_refresh:{user_id}")`) para evitar que dos hilos simultáneos invaliden el token de una cuenta.

---

## 3. Endpoints Principales Utilizados por el ERP

| Módulo ERP | Método | Endpoint Oficial MeLi | Propósito |
| :--- | :--- | :--- | :--- |
| **Órdenes** | `GET` | `/orders/{order_id}` | Consulta comprador, pagos, desglose de comisiones e ítems. |
| **Búsqueda Órdenes**| `GET` | `/orders/search?seller={user_id}&order.status=paid` | Sincronización periódica o reconciliación de ventas. |
| **Publicaciones** | `GET` | `/items/{item_id}` | Obtiene precio, stock, variaciones, título y atributos técnicos. |
| **Actualizar Stock**| `PUT` | `/items/{item_id}` | Actualiza el campo `available_quantity`. |
| **Actualizar Precio**| `PUT` | `/items/{item_id}` | Actualiza el campo `price`. |
| **Envíos** | `GET` | `/shipments/{shipment_id}` | Estado de la paquetería, tracking y modo logístico (Full/Flex). |
| **Guías de Envío** | `GET` | `/shipment_labels?shipment_ids={id}&response_type=pdf` | Descarga de etiqueta en PDF. |
| **Guías Térmicas** | `GET` | `/shipment_labels?shipment_ids={id}&response_type=zpl2` | Descarga de formato ZPL2 para impresoras térmicas Zebra. |
| **Comisiones** | `GET` | `/sites/MLM/listing_prices?price={price}&listing_type_id={type}&category_id={cat}` | Simulación previa de comisiones de venta por categoría. |

---

## 4. Retenciones Fiscales Oficiales de Plataformas en México (SAT)

El motor financiero del ERP aplica las fórmulas del SAT México:
1. **Con RFC Registrado y Validado:**
   - **Retención de IVA:** 8% (la mitad del 16% de IVA trasladado en la venta).
   - **Retención de ISR:** 1% (para personas físicas en régimen RESICO / Actividad Empresarial).
   - **Personas Morales:** Exentas de retención directa de plataforma.
2. **Sin RFC Registrado:**
   - **Retención de IVA:** 16% total.
   - **Retención de ISR:** 20% total.
3. **Fórmula de Rentabilidad Neta:**
   $$\text{Utilidad Neta} = \text{Precio de Venta} - \text{Costo del Producto (COGS)} - \text{Comisión MeLi} - \text{Envío Subsidiado} - \text{Retención IVA} - \text{Retención ISR}$$
