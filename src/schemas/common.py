"""Esquemas comunes y validadores compartidos."""

import re
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

# Expresión regular oficial del SAT para validar RFCs (Personas Físicas y Morales con homoclave)
RFC_REGEX = re.compile(r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$", re.IGNORECASE)


class BaseSchema(BaseModel):
    """Configuración estándar de serialización para Pydantic v2."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ApiResponse(BaseModel):
    """Envoltorio estándar de respuesta exitosa."""

    success: bool = True
    message: str = "Operación realizada con éxito"
    data: Any | None = None
