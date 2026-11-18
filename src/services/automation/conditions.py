"""
Motor de Evaluación Segura de Condiciones para Reglas de Automatización ECA.

Garantiza:
- Evaluación determinista sin ejecución de código arbitrario (sin `eval` ni `exec`).
- Navegación segura por rutas en notación de puntos (dot-notation).
- Soporte para operadores relacionales, pertenencia y rangos.
- Combinación booleana estricta: ALL (AND) y ANY (OR).
"""

from typing import Any


class ConditionEvaluator:
    """Evaluador de condiciones estructuradas sobre el contexto del evento y del ERP."""

    @classmethod
    def get_field_value(cls, context: dict[str, Any], path: str) -> Any:
        """
        Extrae un valor anidado a partir de una ruta en notación punto.
        Ejemplo: "order.total_amount" o "payload.variant.stock_available".
        """
        if not path:
            return None

        # Si el usuario especificó "payload.algo" o directamente "algo"
        tokens = path.split(".")
        current = context

        for token in tokens:
            if isinstance(current, dict):
                if token in current:
                    current = current[token]
                elif "payload" in current and isinstance(current["payload"], dict) and token in current["payload"]:
                    current = current["payload"][token]
                else:
                    return None
            else:
                return None

        return current

    @classmethod
    def evaluate_single(cls, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        """Evalúa una condición individual contra el contexto."""
        field_path = condition.get("field", "")
        operator = condition.get("operator", "eq")
        target_value = condition.get("value")

        actual_value = cls.get_field_value(context, field_path)

        # Operadores de nulidad
        if operator == "is_null":
            return actual_value is None
        if operator == "is_not_null":
            return actual_value is not None

        if actual_value is None:
            # Si el valor no existe en el contexto y el operador no es de nulidad, no cumple
            return False

        # Intentar coerción numérica si ambos son convertibles
        try:
            if isinstance(target_value, (int, float)) and not isinstance(actual_value, bool):
                actual_num = float(actual_value)
                target_num = float(target_value)
                return cls._eval_numeric(actual_num, operator, target_num)
        except (ValueError, TypeError):
            pass

        # Evaluación por tipo estándar
        return cls._eval_standard(actual_value, operator, target_value)

    @classmethod
    def _eval_numeric(cls, actual: float, operator: str, target: float) -> bool:
        if operator == "eq":
            return abs(actual - target) < 1e-6
        elif operator == "neq":
            return abs(actual - target) >= 1e-6
        elif operator == "gt":
            return actual > target
        elif operator == "gte":
            return actual >= target
        elif operator == "lt":
            return actual < target
        elif operator == "lte":
            return actual <= target
        elif operator == "in":
            return False
        return False

    @classmethod
    def _eval_standard(cls, actual: Any, operator: str, target: Any) -> bool:
        if operator == "eq":
            return actual == target
        elif operator == "neq":
            return actual != target
        elif operator == "gt":
            return actual > target
        elif operator == "gte":
            return actual >= target
        elif operator == "lt":
            return actual < target
        elif operator == "lte":
            return actual <= target
        elif operator == "in":
            if isinstance(target, (list, tuple, set)):
                return actual in target
            return str(actual) in str(target)
        elif operator == "nin":
            if isinstance(target, (list, tuple, set)):
                return actual not in target
            return str(actual) not in str(target)
        elif operator == "contains":
            if isinstance(actual, (list, tuple, set)):
                return target in actual
            return str(target).lower() in str(actual).lower()
        elif operator == "between":
            if isinstance(target, (list, tuple)) and len(target) == 2:
                try:
                    return float(target[0]) <= float(actual) <= float(target[1])
                except (ValueError, TypeError):
                    return False
            return False
        return False

    @classmethod
    def evaluate_all(
        cls, conditions: list[dict[str, Any]], match_type: str, context: dict[str, Any]
    ) -> tuple[bool, list[dict[str, Any]]]:
        """
        Evalúa la lista completa de condiciones con operador ALL (AND) o ANY (OR).
        Retorna: (cumplió_todas, snapshot_con_resultados_individuales)
        """
        if not conditions:
            return True, []

        snapshot = []
        results = []

        for cond in conditions:
            passed = cls.evaluate_single(cond, context)
            results.append(passed)
            snap = dict(cond)
            snap["evaluated_passed"] = passed
            snap["actual_value"] = cls.get_field_value(context, cond.get("field", ""))
            snapshot.append(snap)

        if match_type.upper() == "ANY":
            overall = any(results)
        else:  # ALL por defecto
            overall = all(results)

        return overall, snapshot
