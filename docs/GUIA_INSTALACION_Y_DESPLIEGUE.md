# Guía Oficial de Instalación y Despliegue Reproducible
## ERP Inteligente Mercado Libre México & Plataforma SaaS Multiempresa

Esta guía técnica detalla el procedimiento oficial y reproducible para la instalación, configuración y puesta en marcha del ERP en entornos de **Staging** (pre-producción) y **Producción**, garantizando alta disponibilidad, aislamiento de red y cumplimiento de estándares de seguridad (OWASP Top 10 y CIS Benchmarks).

---

## 1. Requisitos de Infraestructura y Sistema

### 1.1 Especificaciones Mínimas de Servidor (Hardware)

| Componente | Requisito Mínimo (Staging / <10 Tenants) | Recomendado para Producción (50-200 Tenants) |
| :--- | :--- | :--- |
| **Arquitectura** | x86_64 / amd64 | x86_64 / amd64 |
| **CPU** | 2 vCPUs | 4 - 8 vCPUs dedicadas |
| **Memoria RAM** | 4 GB | 16 GB - 32 GB ECC |
| **Almacenamiento** | 40 GB SSD NVMe | 200 GB+ SSD NVMe (RAID 10) |
| **Ancho de Banda** | 100 Mbps simétrico | 1 Gbps con protección DDoS |
| **Sistema Operativo** | Ubuntu 22.04 / 24.04 LTS | Ubuntu 24.04 LTS Server / Debian 12 |

### 1.2 Dependencias de Software Requeridas en el Servidor Anfitrión

- **Docker Engine:** Versión 26.0 o superior.
- **Docker Compose Plugin:** Versión 2.27 o superior (`docker compose`).
- **Git:** 2.40+.
- **Curl & OpenSSL:** Para pruebas de conectividad y generación de secretos criptográficos.
- **Puertos de Red Requeridos:**
  - `80/TCP`: HTTP (Redirección automática a HTTPS mediante Caddy).
  - `443/TCP`: HTTPS (Tráfico seguro de clientes y webhooks de Mercado Libre).
  - `8080/TCP` y `8443/TCP`: Exclusivos del entorno Staging (opcional si corre en host separado).
  - `9090/TCP`: Prometheus (acceso local `127.0.0.1` o restringido por VPN/Firewall).

---

## 2. Preparación del Servidor y Repositorio

### Paso 2.1: Clonar el Repositorio Oficial
```bash
cd /opt
sudo git clone https://github.com/tu-organizacion/erp-mercadolibre-mexico.git
cd erp-mercadolibre-mexico
sudo chown -R $USER:$USER .
```

### Paso 2.2: Crear Estructura de Directorios Persistentes
```bash
mkdir -p storage/labels storage/invoices storage/exports
mkdir -p backups/staging backups/production logs/staging logs/production
chmod 700 backups storage
```

---

## 3. Configuración de Variables de Entorno y Claves Maestras

El ERP requiere tres claves criptográficas maestras independientes generadas mediante algoritmos seguros.

### Generación de Secretos Criptográficos:
```bash
# 1. JWT Secret (64 caracteres hexadecimales para sesiones):
openssl rand -hex 32

# 2. Token Encryption Key (Fernet AES-128 para credenciales OAuth de Mercado Libre):
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. Internal API Key (Comunicación de microservicios y workers):
openssl rand -hex 24
```

---

## 4. Despliegue en Entorno Staging (Pre-Producción)

El entorno Staging permite validar nuevas versiones con datos de prueba sin afectar operaciones comerciales activas.

1. **Configurar archivo `.env.staging`:**
   ```bash
   cp .env.staging.example .env.staging
   nano .env.staging
   ```
   *Asigne claves únicas para staging y configure el subdominio `staging.tu-dominio.com`.*

2. **Ejecutar el script automatizado de Staging:**
   ```bash
   chmod +x scripts/*.sh
   ./scripts/deploy_staging.sh
   ```
   *(En entornos Windows PowerShell ejecute `.\scripts\deploy_staging.ps1`)*

3. **Verificación de Staging:**
   ```bash
   curl -I http://localhost:8080/api/v1/health
   curl http://localhost:8080/metrics
   ```

---

## 5. Despliegue en Entorno de Producción

### Paso 5.1: Configurar Variables de Producción (`.env`)
```bash
cp .env.example .env
nano .env
```
Asegúrese de establecer:
- `ENVIRONMENT=production`
- `DOMAIN_NAME=erp.tu-empresa.com.mx`
- `ACME_EMAIL=admin@tu-empresa.com.mx`
- Contraseñas seguras para `POSTGRES_PASSWORD` y `REDIS_PASSWORD` (mínimo 24 caracteres alfanuméricos).
- Credenciales autorizadas de Mercado Libre (`MELI_CLIENT_ID` y `MELI_CLIENT_SECRET`).

### Paso 5.2: Ejecutar el Script de Despliegue de Producción
```bash
./scripts/deploy_prod.sh
```
El script realiza automáticamente:
1. Respaldo de seguridad previo al despliegue.
2. Compilación de imágenes Docker optimizadas en múltiples etapas.
3. Inicio de servicios de base de datos PostgreSQL 16 y Redis 7 con healthchecks activos.
4. Aplicación de migraciones de esquema Alembic (`alembic upgrade head`).
5. Puesta en marcha del proxy Caddy con aprovisionamiento automático de certificados SSL Let's Encrypt.
6. Ejecución de Smoke Tests automáticos contra el endpoint `/api/v1/health`.

---

## 6. Configuración de Dominio y Certificados HTTPS

El proxy inverso Caddy integrado gestiona la emisión y renovación automática de certificados SSL/TLS con Let's Encrypt o ZeroSSL.

### Registro DNS Requerido:
| Tipo | Nombre | Valor | TTL |
| :--- | :--- | :--- | :--- |
| **A** | `erp` | `IP_PUBLICA_DEL_SERVIDOR` | 300 s |
| **A** | `staging` | `IP_PUBLICA_DEL_SERVIDOR` | 300 s |

### Verificación de Cabeceras de Seguridad:
```bash
curl -I https://erp.tu-empresa.com.mx/api/v1/health
```
Debe devolver:
- `HTTP/2 200`
- `strict-transport-security: max-age=31536000; includeSubDomains; preload`
- `x-content-type-options: nosniff`
- `x-frame-options: DENY`
- `referrer-policy: strict-origin-when-cross-origin`

---

## 7. Actualizaciones con Cero Tiempo de Inactividad (Zero-Downtime)

Para actualizar versiones sin desconectar usuarios ni interrumpir la recepción de webhooks de Mercado Libre:

```bash
./scripts/zero_downtime_update.sh
```
El script compila las nuevas imágenes en segundo plano, actualiza de forma escalonada el worker asíncrono y posteriormente reemplaza los procesos web garantizando la finalización de solicitudes HTTP activas.
