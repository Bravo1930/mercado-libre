# Guía Oficial de Mantenimiento Preventivo y Recuperación ante Desastres (Disaster Recovery)
## ERP Inteligente Mercado Libre México & Plataforma SaaS Multiempresa

Este documento establece las políticas operativas, procedimientos de mantenimiento preventivo, protocolos de respuesta ante incidentes y el plan formal de **Recuperación ante Desastres (Disaster Recovery / DR)** para garantizar la continuidad ininterrumpida del negocio y la integridad de los datos financieros, transaccionales y de inventario.

---

## 1. Política Corporativa de Respaldos (Backup Policy)

### 1.1 Objetivos de Continuidad del Servicio
- **RPO (Recovery Point Objective):** $\le 1$ hora. La pérdida máxima admisible de transacciones ante catástrofe total no excederá los 60 minutos.
- **RTO (Recovery Time Objective):** $\le 15$ minutos. El tiempo de restauración operativa del servicio desde el momento del incidente no superará los 15 minutos.

### 1.2 Estrategia de Copias de Seguridad
| Tipo de Respaldo | Frecuencia | Retención | Destino Primario | Destino Secundario (Off-site) |
| :--- | :--- | :--- | :--- | :--- |
| **Transaccional (WAL / DB)** | Cada 6 horas | 14 días | Volumen local `/backups` | Bucket S3 / Cloud Storage Cifrado |
| **Respaldo Lógico Cifrado** | Diario (02:00 UTC) | 30 días | `/backups/production` | Servidor geográficamente remoto |
| **Exportación Maestro SaaS** | Semanal | 90 días | `/backups/archive` | Almacenamiento frío inmutable (Glacier) |

### 1.3 Cifrado e Integridad Criptográfica
1. **Cifrado en Reposo:** Todos los archivos de respaldo son cifrados mediante el estándar simétrico **AES-128-CBC / Fernet** utilizando la clave maestra `TOKEN_ENCRYPTION_KEY`.
2. **Checksum SHA-256:** Cada archivo `.enc` se emite con un archivo de metadatos `.meta.json` y una firma digital hash SHA-256 para prevenir alteraciones o manipulación de datos en tránsito o almacenamiento.

---

## 2. Procedimiento de Recuperación ante Desastres (DR Runbook)

### Paso 2.1: Identificación y Aislamiento del Incidente
1. Declarar el estado de contingencia técnica.
2. Detener las entradas de tráfico externo para evitar estados inconsistentes:
   ```bash
   docker compose stop api worker
   ```

### Paso 2.2: Selección y Verificación del Respaldo
Localice el archivo de respaldo más reciente y compruebe su firma SHA-256:
```bash
cd /opt/erp-mercadolibre-mexico
sha256sum -c backups/production/backup_production_YYYYMMDD_HHMMSS.enc.sha256
```

### Paso 2.3: Ejecución de la Restauración
Ejecute el script automatizado de recuperación:
```bash
./scripts/disaster_recovery.sh backups/production/meli_erp_backup_YYYYMMDD_HHMMSS.sql.gz
```
*(En Windows PowerShell ejecute `.\scripts\disaster_recovery.ps1 -BackupFile .\backups\production\archivo.sql.gz`)*

### Paso 2.4: Verificación Post-Restauración (Smoke Test)
Compruebe la consistencia de los datos ejecutando una consulta de validación de tablas críticas:
```bash
docker compose exec postgres psql -U erp_admin -d meli_erp_db -c "
SELECT table_name, table_schema 
FROM information_schema.tables 
WHERE table_name IN ('companies', 'products', 'inventories', 'orders', 'saas_subscriptions');
"
```

### Paso 2.5: Reanudación de Servicios y Monitoreo
```bash
docker compose up -d
./scripts/health_check.sh
```

---

## 3. Mantenimiento Preventivo y Optimización

### 3.1 Mantenimiento de PostgreSQL 16
Ejecutar semanalmente en horarios de bajo tráfico (Domingos 03:00 am):
```bash
# 1. Limpieza y actualización de estadísticas del planificador de consultas
docker compose exec -T postgres vacuumdb -U erp_admin -d meli_erp_db --analyze --verbose

# 2. Reindexación de índices de búsqueda intensiva (SKUs, IDs de MeLi, órdenes)
docker compose exec -T postgres psql -U erp_admin -d meli_erp_db -c "REINDEX DATABASE meli_erp_db;"
```

### 3.2 Monitoreo y Mantenimiento de Redis 7
- **Política de Memoria:** Configurada en `allkeys-lru` con un límite estricto de `512MB`.
- **Inspección de Claves de Bloqueo y Rate Limiting:**
  ```bash
  docker compose exec redis redis-cli info memory
  docker compose exec redis redis-cli --bigkeys
  ```

### 3.3 Gestión y Depuración de Logs (Log Sanitization)
El middleware nativo del ERP (`SensitiveDataScrubberFilter`) redacta automáticamente credenciales, JWTs, tarjetas y tokens en los logs. Para evitar saturación de disco:
- Los registros se rotan automáticamente al alcanzar 50 MB con un historial máximo de 10 archivos comprimidos.
- Configurar logrotate en el servidor host:
  ```text
  /opt/erp-mercadolibre-mexico/logs/*.log {
      daily
      missingok
      rotate 14
      compress
      delaycompress
      notifempty
      create 0640 appuser appuser
  }
  ```

---

## 4. Matriz de Resolución de Incidentes Críticos (Troubleshooting)

| Incidente | Síntoma Principal | Causa Probable | Acción Correctiva Inmediata |
| :--- | :--- | :--- | :--- |
| **Token OAuth MeLi Expirado** | Errores HTTP 401 en llamadas a la API de Mercado Libre. | El refresh token falló al rotar o la empresa revocó permisos en MeLi. | Ingresar a `/app#settings`, seleccionar la cuenta MeLi y hacer clic en *"Reconectar con Mercado Libre"*. |
| **Saturación de Cola Webhooks** | Retraso en la confirmación de pedidos o stock. | Pico de tráfico o bloqueo temporal de Redis. | Comprobar contenedor worker: `docker compose logs --tail=100 worker`. Escalar worker: `docker compose up -d --scale worker=3`. |
| **Base de Datos No Responde** | Healthcheck `/api/v1/health` devuelve `503 Service Unavailable`. | Conexiones agotadas o falta de memoria RAM. | Revisar conexiones activas: `SELECT count(*) FROM pg_stat_activity;`. Reiniciar contenedor postgres y ajustar `DB_POOL_SIZE`. |
| **Alerta de Ciberseguridad / Bloqueo** | Usuario legítimo recibe HTTP 429 persistente. | Activación preventiva del Rate Limiter por ráfagas de consultas. | Administrador puede reiniciar ventana de rate limit o consultar el incidente en `/app#security`. |
