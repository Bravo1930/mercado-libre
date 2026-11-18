# ERP Inteligente para Mercado Libre México

[![Python](https://img.shields.io/badge/Python-3.13%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D.svg)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

ERP de clase empresarial y arquitectura SaaS multi-empresa diseñado para la gestión integral de operaciones en **Mercado Libre México (MLM)**: inventario unificado, ventas en tiempo real, publicaciones, guías de envío (PDF y ZPL2 térmico), compras, proveedores, sincronización con Google Sheets / Excel, cálculo de comisiones e impuestos del SAT, y automatizaciones asistidas por IA.

---

## 🏛️ Arquitectura del Sistema

El ERP opera bajo un modelo desacoplado y orientado a eventos:
- **Entorno Local (PC):** Diseñado para desarrollo ágil asistido por **Claude Code**, pruebas locales con recarga en caliente (`uv` + FastAPI) y túneles seguros (`cloudflared`).
- **Servidor 24/7 (Producción):** Contenedores Docker orquestados con **Caddy** (HTTPS automático con Let's Encrypt), **FastAPI** como pasarela multi-tenant, **Redis 7** para ingestión ultrarrápida de webhooks (<50ms) y **PostgreSQL 16** como base de datos central relacional.

```
                            ┌────────────────────────┐
                            │ Mercado Libre México   │
                            │ (Webhooks: < 500ms)    │
                            └───────────┬────────────┘
                                        │ HTTPS
                                        ▼
                            ┌────────────────────────┐
                            │ Caddy (Reverse Proxy)  │
                            │ Auto SSL / Let's Enc   │
                            └───────────┬────────────┘
                                        │
                                        ▼
                            ┌────────────────────────┐
                            │ FastAPI Multi-Tenant   │
                            │ Core ERP API           │
                            └───────┬────────┬───────┘
                                    │        │
               ┌────────────────────┘        └────────────────────┐
               ▼                                                  ▼
    ┌─────────────────────┐                            ┌─────────────────────┐
    │ Redis 7             │                            │ PostgreSQL 16       │
    │ Cola de Webhooks    │                            │ Base de Datos       │
    │ Locks de Tokens MeLi│                            │ Multi-Tenant / RLS  │
    └──────────┬──────────┘                            └─────────────────────┘
               │
               ▼
    ┌─────────────────────┐
    │ Background Workers  │ ──► Sincronización Google Sheets / Excel
    │ Ingesta Asíncrona   │ ──► Impresión Térmica ZPL2 / Guías PDF
    │ Rentabilidad SAT MX │ ──► Actualización Masiva de Precios/Stock
    └─────────────────────┘
```

---

## 📁 Estructura del Repositorio

```
rp Mercado Libre/
├── .env.example             # Plantilla de variables de entorno exhaustivamente documentada
├── .env                     # Variables de entorno locales (ignorado por Git)
├── .gitignore               # Reglas estrictas de exclusión de secretos y temporales
├── .gitattributes          # Normalización de saltos de línea (CRLF/LF)
├── pyproject.toml           # Definición de dependencias modernas (PEP 621 / uv)
├── Dockerfile               # Construcción multi-stage de producción (non-root)
├── Dockerfile.dev           # Contenedor de desarrollo con hot-reload
├── docker-compose.yml       # Orquestación de producción (Caddy, API, Worker, DB, Redis)
├── docker-compose.dev.yml   # Sobrescrituras para desarrollo local
├── docker-compose.test.yml  # Entorno aislado para pruebas automatizadas CI/CD
├── Caddyfile                # Configuración de proxy inverso HTTPS
├── config/
│   └── logging.conf         # Configuración de rotación de logs (10MB, 5 backups)
├── docs/
│   ├── INSTALLATION.md      # Guía paso a paso para PC y Servidor 24/7
│   ├── ARCHITECTURE.md      # Documento de arquitectura y modelo de datos
│   └── API_MERCADOLIBRE.md  # Especificaciones técnicas de la API de Mercado Libre
├── scripts/
│   ├── dev.ps1              # Lanzador rápido de desarrollo en Windows
│   ├── backup.sh            # Script de copias de seguridad de PostgreSQL (retención 14 días)
│   ├── restore.sh           # Script de restauración de base de datos
│   └── generate_keys.py     # Generador de claves criptográficas seguras (JWT y AES-256)
├── src/
│   ├── main.py              # Fábrica FastAPI, middlewares y ciclo de vida
│   ├── core/
│   │   ├── config.py        # Settings tipados con Pydantic
│   │   ├── database.py      # SQLAlchemy 2.0 Async + Pool de conexiones
│   │   ├── logging.py       # Sistema de logs rotativos (consola + archivo JSON)
│   │   ├── redis.py         # Cliente Redis, bloqueos distribuidos (Mutex) y colas
│   │   └── security.py      # Cifrado AES-256 (Fernet) de tokens y hashing bcrypt
│   ├── models/
│   │   ├── tenant.py        # Tenants (SaaS) y Companies (RFCs México)
│   │   ├── meli_account.py  # Cuentas de vendedor vinculadas a MeLi
│   │   ├── product.py       # Catálogo maestro SKU y publicaciones MeLi
│   │   └── order.py         # Órdenes de venta y auditoría de rentabilidad neta SAT
│   ├── api/v1/
│   │   ├── health.py        # Endpoint de salud y diagnóstico integral
│   │   ├── webhooks.py      # Ingesta ultrarrápida de notificaciones MeLi
│   │   └── auth.py          # Flujo OAuth 2.0 oficial para Mercado Libre
│   └── workers/
│       └── tasks.py         # Worker en segundo plano para tareas asíncronas
├── storage/                 # Volúmenes persistentes de guías, importaciones y exportaciones
├── logs/                    # Directorio de logs rotativos
├── backups/                 # Almacenamiento de snapshots de base de datos
└── tests/                   # Pruebas automatizadas unitarias y de integración
```

---

## 🚀 Inicio Rápido en PC de Desarrollo

### 1. Iniciar con `uv` (Local Rápido)
```powershell
# Instalar dependencias
C:\Users\Asus\.local\bin\uv.exe pip install -e ".[dev]"

# Iniciar el servidor API
uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```
- **Swagger UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check:** [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

### 2. Iniciar con Docker
```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

---

## 🧪 Pruebas Automatizadas

Para ejecutar la batería completa de pruebas:
```powershell
pytest -v --cov=src
```

O en un entorno de contenedores completamente aislado:
```bash
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

---

## 🔒 Seguridad y Encriptación de Tokens

Mercado Libre utiliza **Refresh Tokens rotativos de un solo uso** con validez de 6 horas.
1. Todos los tokens se encriptan en reposo usando **AES-256 (Fernet)** en PostgreSQL.
2. Cada renovación se protege mediante un **Mutex Distribuido en Redis**, garantizando que nunca se produzca una condición de carrera que invalide la cuenta del vendedor.

---

## 📖 Documentación Completa
- [Guía de Instalación y Despliegue en Servidor](docs/INSTALLATION.md)
- [Arquitectura de Software y Modelo de Datos](docs/ARCHITECTURE.md)
- [Integración con Mercado Libre México y Normativa SAT](docs/API_MERCADOLIBRE.md)
