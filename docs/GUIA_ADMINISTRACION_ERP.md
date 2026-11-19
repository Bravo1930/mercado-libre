# Guía Oficial de Administración del ERP & Plataforma SaaS Multiempresa
## Manual Operativo para Administradores de Plataforma y Administradores de Tenant

Esta guía proporciona las instrucciones funcionales y técnicas para la gestión integral de la plataforma, administración de clientes, asignación de permisos, configuración de reglas comerciales y monitoreo de seguridad.

---

## 1. Jerarquía de Roles y Modelo de Accesos (RBAC)

El ERP implementa un control de acceso basado en roles con validación de tenancy estricta:

| Rol | Alcance | Capacidades Principales |
| :--- | :--- | :--- |
| **`platform_owner`** | Global (SaaS) | Acceso irrestricto al Panel Global SaaS, gestión de planes comerciales, métricas MRR/ARR, políticas globales de seguridad y recuperación. |
| **`saas_admin`** | Global (SaaS) | Onboarding de nuevas empresas, ajuste de cuotas, suspensión/reactivación de suscripciones y soporte técnico. |
| **`company_admin`** | Empresa (Tenant) | Configuración de la empresa, vinculación de cuentas de Mercado Libre, gestión de almacenes, usuarios de la empresa y reglas comerciales. |
| **`operator`** | Empresa (Tenant) | Operación diaria: recepción de pedidos, impresión de etiquetas, surtido de almacén, recepción de órdenes de compra y actualización de stock. |
| **`auditor`** | Empresa (Tenant) | Acceso de solo lectura al Centro Tabular, reportes de rentabilidad, conciliación contable y logs de auditoría. |

---

## 2. Gestión de Suscripciones SaaS y Control de Cuotas

### 2.1 Planes Comerciales Predeterminados
1. **Plan Básico:** Diseñado para vendedores emergentes.
   - Hasta 2 usuarios por empresa.
   - 1 cuenta de Mercado Libre conectada.
   - 2 GB de almacenamiento.
   - Hasta 500 pedidos procesados por mes.
2. **Plan Profesional:** Diseñado para empresas medianas con múltiples bodegas.
   - Hasta 10 usuarios por empresa.
   - 3 cuentas de Mercado Libre conectadas.
   - 15 GB de almacenamiento.
   - Hasta 5,000 pedidos procesados por mes.
   - Acceso al Asistente Comercial de IA y Motor de Automatizaciones ECA.
3. **Plan Empresarial (Enterprise):** Para grandes operaciones logísticas y marcas oficiales.
   - Usuarios, cuentas MeLi y pedidos ilimitados (o cotización custom).
   - 100 GB de almacenamiento.
   - Soporte prioritario y SLA del 99.9%.

### 2.2 Validación Automática de Cuotas (`QuotaEnforcementService`)
- Si una empresa excede su cuota mensual de pedidos o usuarios, el sistema bloquea operaciones adicionales y genera una notificación administrativa invitando a un upgrade.
- En caso de mora o suspensión de suscripción, el sistema aplica un bloqueo de escritura (`HTTP 402 Payment Required`), permitiendo únicamente la consulta y exportación de datos históricos.

---

## 3. Conexión y Administración de Mercado Libre México

### 3.1 Flujo de Autorización OAuth 2.0
1. Navegue a `/app#settings` > **Cuentas de Mercado Libre**.
2. Haga clic en **"Vincular Nueva Cuenta MeLi"**.
3. El sistema redirigirá al portal oficial de autenticación de Mercado Libre México.
4. Tras autorizar, el sistema captura el `code`, intercambia por Access Token y Refresh Token, los encripta mediante AES-Fernet y registra el ID de vendedor.

### 3.2 Sincronización Automática de Publicaciones y Webhooks
- Los webhooks oficiales de MeLi notifican en tiempo real los tópicos: `orders_v2`, `items`, `shipments`, `payments`.
- El ERP responde con código `HTTP 200` en menos de 500ms y delega el procesamiento a la cola de Redis para garantizar cero pérdida de eventos.
- Si la conexión externa experimenta latencia o desconexión, el motor de reconciliación nocturno ejecuta un barrido diferencial para asegurar sincronía 100%.

---

## 4. Motor de Automatizaciones ECA (Event-Condition-Action)

### 4.1 Reglas Comerciales Configurables
El ERP permite habilitar reglas predefinidas en modalidad manual, automática o con aprobación previa:
- **Reserva Inmediata de Stock:** Reserva automáticamente existencia física al confirmarse un pago.
- **Protección de Margen Mínimo:** Detiene cambios masivos de precios si el margen resultante cae por debajo del 15%.
- **Alerta Preventiva de Reposición:** Dispara órdenes de compra sugeridas cuando el stock proyectado cruza el punto de reorden.

### 4.2 Interruptor de Emergencia (Kill Switch)
En caso de anomalías operativas o errores de configuración humana, el administrador puede accionar el **Kill Switch General** en `/app#automations`, deteniendo inmediatamente toda ejecución automática sin afectar la operación manual.

---

## 5. Centro de Ciberseguridad y Monitoreo SIEM

El módulo `/app#security` proporciona al equipo de seguridad:
- Registro en tiempo real de incidentes de seguridad (intentos de inyección SQL, forcejeo de contraseñas, anomalías de sesión).
- Control de sesiones activas con revocación multi-dispositivo con un solo clic.
- Generación de respaldos cifrados bajo demanda y ejecución de simulacros de Disaster Recovery.
