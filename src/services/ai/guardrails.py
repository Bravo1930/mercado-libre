"""
Módulo de Seguridad y Protección contra Prompt Injection y Accesos No Autorizados.

Implementa:
- Sanitización de entradas del usuario.
- Detección determinista de patrones de evasión (Jailbreak, DAN, Role reversal).
- Bloqueo de inyecciones SQL / consultas directas a la base de datos.
- Supresión de delimitadores engañosos de modelos LLM.
- Prevención de exfiltración de credenciales y variables de entorno.
"""

from dataclasses import dataclass
import re
import unicodedata


@dataclass
class GuardrailResult:
    """Resultado del análisis de seguridad de un prompt o mensaje."""
    is_safe: bool
    sanitized_text: str
    violation_type: str | None = None
    reason: str | None = None


class PromptInjectionGuard:
    """
    Guardián de seguridad multicapa para el asistente de IA.
    Examina las entradas antes de enviarlas al modelo o a las herramientas autorizadas.
    """

    # 1. Patrones de evasión y anulación de instrucciones del sistema
    _PROMPT_OVERRIDE_PATTERNS = [
        re.compile(r"(?:ignore|forget|disregard|bypass|overwrite)\s+(?:all\s+)?(?:previous|past|prior|above|system)\s+(?:instructions|prompts|rules|commands)", re.IGNORECASE),
        re.compile(r"(?:act\s+as|pretend\s+(?:to\s+be|you\s+are)|you\s+are\s+now)\s+(?:an?\s+unrestricted|a\s+hacker|dan|jailbreak|developer\s+mode|root|administrator)", re.IGNORECASE),
        re.compile(r"(?:system\s*(?:prompt|override|command)\s*:|\[\s*system\s*\]|<\|im_start\|>system|<\|system\|>)", re.IGNORECASE),
        re.compile(r"(?:do\s+anything\s+now|jailbroken|unfiltered\s+mode)", re.IGNORECASE),
    ]

    # 2. Patrones de acceso directo a base de datos y SQL Injection
    _SQL_INJECTION_PATTERNS = [
        re.compile(r"\b(?:union\s+select|select\s+.+\s+from|insert\s+into|delete\s+from|drop\s+table|alter\s+table|update\s+.+\s+set)\b", re.IGNORECASE),
        re.compile(r"\b(?:information_schema|sqlite_master|pg_tables|pg_stat|pg_catalog|sys\.databases)\b", re.IGNORECASE),
        re.compile(r"(?:--\s*$|;\s*(?:select|drop|insert|delete)|'\s*or\s*'1'\s*=\s*'1)", re.IGNORECASE),
        re.compile(r"\b(?:execute\s*\(|xp_cmdshell|exec\s*sp_)\b", re.IGNORECASE),
    ]

    # 3. Patrones de exfiltración de secretos o credenciales
    _EXFILTRATION_PATTERNS = [
        re.compile(r"(?:reveal|print|show|dump|leak|output|exfiltrate|give\s+me)\s+(?:the\s+|your\s+)?.*?(?:system\s+prompt|api\s*key|database\s+password|secret\s+key|encryption\s+key|jwt\s+secret|env\s+variables)", re.IGNORECASE),
        re.compile(r"(?:mu[eé]strame|dime|revela|imprime|dame)\s+(?:el\s+|tu\s+)?.*?(?:system\s+prompt|prompt\s+del\s+sistema|clave\s+secreta|api\s*key|contrase[ñn]a\s+de\s+la\s+base\s+de\s+datos)", re.IGNORECASE),
    ]

    # 4. Delimitadores de control de tokens en LLMs modernos
    _DELIMITER_PATTERNS = [
        re.compile(r"<\|im_start\|>", re.IGNORECASE),
        re.compile(r"<\|im_end\|>", re.IGNORECASE),
        re.compile(r"<\|endoftext\|>", re.IGNORECASE),
        re.compile(r"\[/?INST\]", re.IGNORECASE),
        re.compile(r"```system", re.IGNORECASE),
    ]

    @classmethod
    def check_and_sanitize(cls, user_text: str) -> GuardrailResult:
        """
        Analiza y sanitiza el texto del usuario.
        Si detecta patrones maliciosos, marca is_safe=False con el motivo.
        """
        if not user_text or not user_text.strip():
            return GuardrailResult(is_safe=True, sanitized_text="")

        # Normalizar caracteres Unicode y eliminar caracteres de control invisibles
        normalized = unicodedata.normalize("NFKC", user_text)
        cleaned = "".join(c for c in normalized if unicodedata.category(c)[0] != "C" or c in ("\n", "\t", "\r"))
        stripped = cleaned.strip()

        # 1. Verificar intentos de sobrescritura de instrucciones / jailbreak
        for pattern in cls._PROMPT_OVERRIDE_PATTERNS:
            if pattern.search(stripped):
                return GuardrailResult(
                    is_safe=False,
                    sanitized_text=stripped,
                    violation_type="PROMPT_INJECTION_OVERRIDE",
                    reason="Se detectó un intento de anulación de instrucciones o suplantación de rol del sistema.",
                )

        # 2. Verificar intentos de SQL Injection / acceso irrestricto a BD
        for pattern in cls._SQL_INJECTION_PATTERNS:
            if pattern.search(stripped):
                return GuardrailResult(
                    is_safe=False,
                    sanitized_text=stripped,
                    violation_type="SQL_DATABASE_PROBE",
                    reason="Acceso directo o consultas SQL no permitidas. El asistente opera únicamente mediante herramientas de backend autorizadas.",
                )

        # 3. Verificar intentos de exfiltración de credenciales
        for pattern in cls._EXFILTRATION_PATTERNS:
            if pattern.search(stripped):
                return GuardrailResult(
                    is_safe=False,
                    sanitized_text=stripped,
                    violation_type="CREDENTIAL_EXFILTRATION",
                    reason="Solicitud bloqueada por motivos de seguridad: las credenciales y el system prompt no son accesibles.",
                )

        # 4. Sanitizar delimitadores especiales para evitar confusión del LLM
        for pattern in cls._DELIMITER_PATTERNS:
            stripped = pattern.sub("", stripped)

        return GuardrailResult(
            is_safe=True,
            sanitized_text=stripped,
        )
