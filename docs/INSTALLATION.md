# Guía de Instalación y Despliegue: ERP Mercado Libre México

Este documento detalla la instalación, ejecución y mantenimiento del ERP en dos entornos:
1. **Entorno Local (PC de Desarrollo con Windows 11 y Claude Code)**
2. **Entorno de Producción (Servidor Linux 24/7 con Docker y Caddy HTTPS)**

---

## 1. Entorno de Desarrollo Local (PC)

### Requisitos Previos Detectados en tu PC
- **Python 3.13 / 3.11** con el gestor **Astral `uv`** (ubicado en `C:\Users\Asus\.local\bin\uv.exe`).
- **Git** (`git version 2.55+`).
- **Claude Code CLI** (`2.1.310`).
- **Docker Desktop** (opcional para levantar base de datos en contenedores).

### Opción A: Ejecución Nativa con `uv` (Recomendada para Desarrollo Rápido)

1. **Crear y activar el entorno virtual con uv:**
   ```powershell
   # Desde la carpeta del proyecto C:\Users\Asus\rp Mercado Libre
   C:\Users\Asus\.local\bin\uv.exe venv .venv
   .\.venv\Scripts\activate
   ```

2. **Instalar dependencias del proyecto:**
   ```powershell
   C:\Users\Asus\.local\bin\uv.exe pip install -e ".[dev]"
   ```

3. **Verificar configuración del archivo `.env`:**
   Asegúrate de que el archivo `.env` esté configurado con tus credenciales de desarrollo. Puedes generar nuevas claves seguras con:
   ```powershell
   python scripts/generate_keys.py
   ```

4. **Ejecutar el servidor API con recarga en caliente (Hot Reload):**
   ```powershell
   uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
   ```
   - API y Documentación Interactiva (Swagger): [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
   - Diagnóstico de Salud: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

5. **Ejecutar el Worker de segundo plano (en una terminal separada):**
   ```powershell
   python -m src.workers.tasks
   ```

6. **Ejecutar la suite de pruebas automatizadas:**
   ```powershell
   pytest -v --cov=src
   ```

---

### Opción B: Ejecución Local Completa con Docker Compose

Si deseas que PostgreSQL 16 y Redis 7 corran aislados en contenedores:
```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```
Para detener los servicios:
```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

---

## 2. Entorno de Producción Permanente (Servidor 24/7)

### Especificaciones del Servidor
- **SO:** Ubuntu Server 24.04 LTS (x86_64)
- **CPU:** 2 a 4 vCPUs
- **RAM:** 4 a 8 GB
- **Almacenamiento:** 80 a 160 GB SSD NVMe
- **Puertos requeridos abiertos en Firewall (UFW):**
  - `80/tcp` (HTTP - Redirección Caddy / Let's Encrypt)
  - `443/tcp` (HTTPS - Tráfico seguro)
  - `22/tcp` (SSH - Acceso administrativo seguro por llave pública)

### Pasos de Despliegue en Servidor

1. **Instalar Docker y Docker Compose en Ubuntu:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y curl git ufw ca-certificates
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   ```

2. **Configurar Firewall (UFW):**
   ```bash
   sudo ufw default deny incoming
   sudo ufw default allow outgoing
   sudo ufw allow 22/tcp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

3. **Clonar el Repositorio en `/opt/meli-erp`:**
   ```bash
   sudo mkdir -p /opt/meli-erp
   sudo chown $USER:$USER /opt/meli-erp
   git clone <URL_REPOSITORIO> /opt/meli-erp
   cd /opt/meli-erp
   ```

4. **Configurar Variables de Producción:**
   ```bash
   cp .env.example .env
   # Editar con nano o vim:
   nano .env
   ```
   - Configura `ENVIRONMENT=production`
   - Configura `DOMAIN_NAME=erp.tu-empresa.com`
   - Configura `ACME_EMAIL=admin@tu-empresa.com`
   - Genera contraseñas fuertes para PostgreSQL y Redis
   - Genera claves seguras con `python3 scripts/generate_keys.py`

5. **Iniciar los Servicios en Segundo Plano:**
   ```bash
   docker compose up -d --build
   ```

6. **Verificar el Estado de los Contenedores:**
   ```bash
   docker compose ps
   docker compose logs -f api
   ```

7. **Configurar Respaldo Diario Automatizado (Cron):**
   Edita la tabla de cron del servidor:
   ```bash
   sudo crontab -e
   ```
   Agrega la siguiente línea para respaldar la base de datos todos los días a las 03:00 AM (hora CDMX):
   ```cron
   0 3 * * * cd /opt/meli-erp && docker compose exec -T postgres /bin/sh /scripts/backup.sh >> /opt/meli-erp/logs/backup_cron.log 2>&1
   ```

---

## 3. Comandos Útiles de Operación y Diagnóstico

| Acción | Comando Docker (Producción) | Comando Local (PC) |
| :--- | :--- | :--- |
| **Ver logs en tiempo real** | `docker compose logs -f` | Leer `logs/erp.log` |
| **Reiniciar el API** | `docker compose restart api` | Reiniciar proceso uvicorn |
| **Detener todo el sistema** | `docker compose down` | `Ctrl + C` en terminales |
| **Ejecutar Pruebas CI/CD** | `docker compose -f docker-compose.test.yml up --abort-on-container-exit` | `pytest -v` |
| **Generar Respaldo DB** | `docker compose exec postgres /bin/sh /scripts/backup.sh` | N/A |
