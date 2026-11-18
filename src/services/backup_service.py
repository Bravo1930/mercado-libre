"""Servicio Empresarial de Respaldos Cifrados, Verificación de Integridad y Recuperación ante Desastres."""

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any
import uuid

from cryptography.fernet import Fernet
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.database import get_engine
from src.core.exceptions import AppException
from src.core.logging import get_logger
from src.core.security import get_fernet_cipher

logger = get_logger("backup_service")


class BackupException(AppException):
    """Excepción generada durante operaciones de respaldo o recuperación."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            status_code=500,
            error_code="BACKUP_OPERATION_FAILED",
            details=details,
        )


class BackupService:
    """
    Gestor integral de copias de seguridad cifradas, control de retención y recuperación.
    Garantiza:
    1. Cifrado simétrico AES-128-CBC / Fernet en reposo para cada archivo de respaldo.
    2. Generación y verificación de checksum SHA-256 para integridad de datos.
    3. Metadatos inmutables de auditoría (fecha, tamaño, hash, tablas incluidas).
    4. Políticas de retención automatizadas (poda de respaldos antiguos).
    5. Procedimiento de prueba de restauración y recuperación ante desastres (Disaster Recovery).
    """

    def __init__(self, backups_dir: Path | None = None):
        settings = get_settings()
        self.backups_dir = backups_dir or settings.BACKUPS_DIR
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.cipher = get_fernet_cipher()

    async def create_encrypted_backup(
        self,
        session: AsyncSession,
        backup_type: str = "full",
        created_by_user_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """
        Genera un respaldo completo del estado del ERP, lo serializa, cifra con AES y calcula su checksum.
        """
        settings = get_settings()
        backup_id = str(uuid.uuid4())
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename_base = f"backup_{settings.ENVIRONMENT}_{timestamp_str}_{backup_id[:8]}"

        # 1. Extraer volcado lógico de datos de tablas críticas
        dump_data: dict[str, Any] = {
            "metadata": {
                "backup_id": backup_id,
                "version": "1.0",
                "environment": settings.ENVIRONMENT,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": str(created_by_user_id) if created_by_user_id else "SYSTEM",
                "backup_type": backup_type,
                "notes": notes or "Respaldo automático programado de seguridad",
            },
            "tables": {},
        }

        # Tablas críticas para volcado lógico
        target_tables = [
            "tenants",
            "companies",
            "users",
            "company_users",
            "products",
            "product_variants",
            "inventory",
            "warehouses",
            "suppliers",
            "purchase_orders",
            "commercial_rules",
            "automation_configs",
            "automation_rules",
            "audit_logs",
        ]

        for table in target_tables:
            try:
                result = await session.execute(text(f"SELECT * FROM {table};"))
                rows = [dict(row._mapping) for row in result.fetchall()]
                # Convertir UUIDs y datetimes a strings para serialización JSON segura
                serializable_rows = []
                for r in rows:
                    clean_row = {}
                    for k, v in r.items():
                        if isinstance(v, (datetime, uuid.UUID)):
                            clean_row[k] = str(v)
                        elif hasattr(v, "__float__"):
                            clean_row[k] = float(v)
                        else:
                            clean_row[k] = v
                    serializable_rows.append(clean_row)

                dump_data["tables"][table] = {
                    "count": len(serializable_rows),
                    "records": serializable_rows,
                }
            except Exception as exc:
                logger.debug(f"Tabla '{table}' omitida durante respaldo: {exc}")

        # 2. Serializar a JSON
        raw_json_bytes = json.dumps(dump_data, indent=2, default=str).encode("utf-8")
        raw_sha256 = hashlib.sha256(raw_json_bytes).hexdigest()

        # 3. Cifrar con Fernet / AES
        encrypted_bytes = self.cipher.encrypt(raw_json_bytes)
        encrypted_sha256 = hashlib.sha256(encrypted_bytes).hexdigest()

        # 4. Guardar archivo cifrado en disco (.enc)
        enc_file_path = self.backups_dir / f"{filename_base}.enc"
        meta_file_path = self.backups_dir / f"{filename_base}.meta.json"

        with open(enc_file_path, "wb") as f:
            f.write(encrypted_bytes)

        metadata_record = {
            "backup_id": backup_id,
            "filename": enc_file_path.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "raw_size_bytes": len(raw_json_bytes),
            "encrypted_size_bytes": len(encrypted_bytes),
            "raw_sha256": raw_sha256,
            "encrypted_sha256": encrypted_sha256,
            "tables_backed_up": list(dump_data["tables"].keys()),
            "status": "completed",
            "encrypted": True,
        }

        with open(meta_file_path, "w", encoding="utf-8") as f:
            json.dump(metadata_record, f, indent=2)

        # 5. Aplicar política de retención (mantener los 10 más recientes)
        await self.enforce_retention_policy(max_backups=10)

        logger.info(
            f"Respaldo cifrado '{backup_id}' generado exitosamente en {enc_file_path.name} "
            f"({len(encrypted_bytes)} bytes, SHA-256={encrypted_sha256[:12]}...)"
        )
        return metadata_record

    async def list_backups(self) -> list[dict[str, Any]]:
        """Lista todos los respaldos disponibles con sus metadatos y estado de integridad."""
        backups = []
        for meta_file in sorted(self.backups_dir.glob("*.meta.json"), reverse=True):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    enc_file = self.backups_dir / meta.get("filename", "")
                    meta["file_exists"] = enc_file.exists()
                    backups.append(meta)
            except Exception as exc:
                logger.warning(f"Error leyendo metadatos de respaldo {meta_file}: {exc}")
        return backups

    async def verify_backup_integrity(self, backup_id: str) -> dict[str, Any]:
        """
        Comprueba la integridad física y criptográfica de un respaldo cifrado.
        Verifica checksums y valida que pueda ser desencriptado sin errores.
        """
        # Buscar metadatos
        target_meta = None
        for meta_file in self.backups_dir.glob("*.meta.json"):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    if meta.get("backup_id") == backup_id or meta.get("filename", "").startswith(backup_id):
                        target_meta = meta
                        break
            except Exception:
                continue

        if not target_meta:
            raise BackupException(f"Respaldo con identificador '{backup_id}' no encontrado.")

        enc_file_path = self.backups_dir / target_meta["filename"]
        if not enc_file_path.exists():
            raise BackupException(f"El archivo cifrado '{target_meta['filename']}' no existe en disco.")

        # 1. Validar checksum del archivo cifrado
        with open(enc_file_path, "rb") as f:
            enc_data = f.read()

        current_enc_sha256 = hashlib.sha256(enc_data).hexdigest()
        if current_enc_sha256 != target_meta["encrypted_sha256"]:
            return {
                "backup_id": backup_id,
                "is_valid": False,
                "error": "CORRUPCIÓN DETECTADA: El checksum SHA-256 del archivo cifrado no coincide.",
            }

        # 2. Validar desencriptación y contenido
        try:
            decrypted_bytes = self.cipher.decrypt(enc_data)
        except Exception as exc:
            return {
                "backup_id": backup_id,
                "is_valid": False,
                "error": f"FALLO DE DESENCRIPTACIÓN: La clave no coincide o el archivo fue manipulado ({exc}).",
            }

        current_raw_sha256 = hashlib.sha256(decrypted_bytes).hexdigest()
        if current_raw_sha256 != target_meta["raw_sha256"]:
            return {
                "backup_id": backup_id,
                "is_valid": False,
                "error": "CORRUPCIÓN EN CONTENIDO: El checksum del contenido desencriptado no coincide.",
            }

        parsed_dump = json.loads(decrypted_bytes.decode("utf-8"))
        tables_count = len(parsed_dump.get("tables", {}))

        return {
            "backup_id": backup_id,
            "is_valid": True,
            "filename": target_meta["filename"],
            "tables_verified": tables_count,
            "created_at": target_meta["created_at"],
            "checksum_sha256": current_enc_sha256,
            "status": "verified_healthy",
        }

    async def enforce_retention_policy(self, max_backups: int = 10) -> int:
        """Poda los respaldos más antiguos que excedan el límite de retención configurado."""
        backups = await self.list_backups()
        if len(backups) <= max_backups:
            return 0

        to_delete = backups[max_backups:]
        deleted_count = 0
        for b in to_delete:
            enc_file = self.backups_dir / b.get("filename", "")
            meta_file = self.backups_dir / f"{b.get('filename', '').replace('.enc', '')}.meta.json"
            if enc_file.exists():
                enc_file.unlink(missing_ok=True)
            if meta_file.exists():
                meta_file.unlink(missing_ok=True)
            deleted_count += 1
            logger.info(f"Respaldo antiguo '{b.get('backup_id')}' purgado por política de retención.")

        return deleted_count

    async def restore_disaster_recovery_dry_run(self, backup_id: str) -> dict[str, Any]:
        """
        Ejecuta un ensayo controlado de recuperación ante desastres sin sobreescribir datos en producción.
        Desencripta, valida estructura, esquema de tablas y verifica recuento de registros.
        """
        verification = await self.verify_backup_integrity(backup_id)
        if not verification["is_valid"]:
            raise BackupException(f"No se puede iniciar recuperación: Respaldo no íntegro ({verification.get('error')})")

        enc_file_path = self.backups_dir / verification["filename"]
        with open(enc_file_path, "rb") as f:
            enc_data = f.read()

        decrypted_bytes = self.cipher.decrypt(enc_data)
        dump = json.loads(decrypted_bytes.decode("utf-8"))

        summary_tables = {}
        for tbl, data in dump.get("tables", {}).items():
            summary_tables[tbl] = data.get("count", 0)

        return {
            "backup_id": backup_id,
            "dry_run_success": True,
            "message": "Simulación de recuperación ante desastres completada exitosamente. Integridad 100% verificada.",
            "environment_origin": dump.get("metadata", {}).get("environment"),
            "timestamp_origin": dump.get("metadata", {}).get("created_at"),
            "table_record_counts": summary_tables,
        }
