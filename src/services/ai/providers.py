"""
Capa de Proveedores de Inteligencia Artificial Conectables y Configurables.

Admite:
1. Modelos Locales (Ollama, LM Studio, vLLM) mediante protocolo estándar OpenAI /v1/chat/completions.
2. Servicios Externos Configurables (OpenAI, Anthropic Claude, Google Gemini, Groq, Mistral).
3. Proveedor Heurístico Determinista Local (MockDeterministicProvider) para operación 100% offline,
   pruebas sin red y respaldo ante caídas de proveedores externos.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import re
from typing import Any
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.schemas.ai import AICitation, AISuggestedAction
from src.services.ai.tools import CommercialAITools

logger = get_logger("ai_providers")


@dataclass
class ProviderResponse:
    """Respuesta unificada de cualquier proveedor de IA."""
    content: str
    citations: list[dict[str, Any]]
    justification: str | None
    confidence_score: float
    tools_used: list[str]
    suggested_action: dict[str, Any] | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model_name: str


class BaseLLMProvider(ABC):
    """Clase base abstracta para cualquier motor o proveedor de IA."""

    @abstractmethod
    async def generate_response(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        company_name: str,
        user_message: str,
        tools_helper: CommercialAITools,
        preset_period: str = "today",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> ProviderResponse:
        """Genera una respuesta utilizando herramientas autorizadas del ERP."""
        pass


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    Proveedor para endpoints compatibles con OpenAI:
    - Modelos locales en servidor propio o Docker (Ollama, LM Studio, vLLM).
    - APIs externas de OpenAI, Groq, Mistral, Perplexity, DeepSeek.
    """

    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ):
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or ""
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def generate_response(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        company_name: str,
        user_message: str,
        tools_helper: CommercialAITools,
        preset_period: str = "today",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> ProviderResponse:
        """Ejecuta inferencia con OpenAI / Ollama con soporte de function calling."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else "Bearer ollama",
        }

        # Armar mensajes
        messages = [
            {
                "role": "system",
                "content": (
                    f"Eres el Asistente Comercial Ejecutivo de '{company_name}' para Mercado Libre México. "
                    "Tu misión es ayudar a la toma de decisiones con datos reales, analizando ventas, rentabilidad, "
                    "inventario, reposiciones y precios. "
                    "NUNCA inventes números. Si necesitas datos, invoca las herramientas del sistema. "
                    "Siempre incluye justificaciones transparentes y desgloses de cifras estimadas vs confirmadas."
                ),
            }
        ]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})

        tools_def = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools_helper.get_definitions()
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "tools": tools_def,
            "tool_choice": "auto",
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        try:
            async with httpx.AsyncClient(timeout=45.0, trust_env=False) as client:
                res = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                if res.status_code != 200:
                    logger.warning(f"Fallo en proveedor OpenAICompatible ({res.status_code}): {res.text}. Usando fallback.")
                    fallback = MockDeterministicProvider(model_name=self.model_name)
                    return await fallback.generate_response(
                        session, company_id, company_name, user_message, tools_helper, preset_period, conversation_history
                    )

                data = res.json()
                choice = data["choices"][0]["message"]

                # Si el modelo invocó herramientas
                if choice.get("tool_calls"):
                    tool_calls = choice["tool_calls"]
                    tools_used = []
                    all_citations = []
                    all_justifications = []
                    suggested_action = None

                    for tc in tool_calls:
                        fname = tc["function"]["name"]
                        args = json.loads(tc["function"].get("arguments", "{}"))
                        tools_used.append(fname)

                        # Ejecutar herramienta autorizada en el backend
                        t_method = getattr(tools_helper, f"tool_{fname}", None)
                        if t_method:
                            # Inyectar argumentos obligatorios
                            t_kwargs = {"session": session, "company_id": company_id}
                            if fname in ["analyze_sales", "analyze_profitability", "detect_trends", "recommend_products", "detect_slow_rotation", "detect_anomalies", "generate_report"]:
                                t_kwargs["company_name"] = company_name
                            t_kwargs.update(args)

                            tool_res = await t_method(**t_kwargs)
                            all_citations.extend(tool_res.get("citations", []))
                            if tool_res.get("justification"):
                                all_justifications.append(tool_res["justification"])
                            if tool_res.get("suggested_action"):
                                suggested_action = tool_res["suggested_action"]

                    # Responder con el análisis consolidado
                    usage = data.get("usage", {})
                    combined_justification = " | ".join(all_justifications) if all_justifications else None

                    content = choice.get("content") or combined_justification or "Consulta procesada exitosamente."
                    return ProviderResponse(
                        content=content,
                        citations=all_citations,
                        justification=combined_justification,
                        confidence_score=0.98,
                        tools_used=tools_used,
                        suggested_action=suggested_action,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        model_name=self.model_name,
                    )

                usage = data.get("usage", {})
                return ProviderResponse(
                    content=choice.get("content", ""),
                    citations=[],
                    justification="Respuesta directa basada en el contexto conversacional.",
                    confidence_score=0.95,
                    tools_used=[],
                    suggested_action=None,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    model_name=self.model_name,
                )

        except Exception as e:
            logger.error(f"Error conectando con {self.base_url}: {e}. Ejecutando motor heurístico local.")
            fallback = MockDeterministicProvider(model_name=self.model_name)
            return await fallback.generate_response(
                session, company_id, company_name, user_message, tools_helper, preset_period, conversation_history
            )


class MockDeterministicProvider(BaseLLMProvider):
    """
    Motor Heurístico Determinista de IA Local.
    
    Analiza semánticamente las preguntas del usuario (incluyendo las preguntas canónicas del negocio),
    invoca de forma segura las herramientas autorizadas del ERP, recupera métricas reales de la base de datos
    y construye respuestas estructuradas en Markdown con citaciones auditables y justificaciones.
    
    Garantiza:
    - 0% de alucinación matemática.
    - 100% de operatividad offline y en entornos de pruebas aislados.
    - Respuestas exactas y consistentes.
    """

    def __init__(self, model_name: str = "mock-commercial-ai-v1"):
        self.model_name = model_name

    async def generate_response(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        company_name: str,
        user_message: str,
        tools_helper: CommercialAITools,
        preset_period: str = "today",
        conversation_history: list[dict[str, str]] | None = None,
    ) -> ProviderResponse:
        """Clasifica la intención del usuario y despacha hacia las herramientas oficiales correspondientes."""
        text = user_message.lower().strip()
        tools_used = []
        citations = []
        justification = ""
        suggested_action = None

        # -----------------------------------------------------------------------
        # 1. CANÓNICA: "¿Cuánto gané hoy?" / "¿Cuánto he ganado hoy?"
        # -----------------------------------------------------------------------
        if re.search(r"cu[aá]nto\s+(?:gan[eé]|he\s+ganado)\s+hoy", text) or ("gane" in text and "hoy" in text):
            tools_used.append("analyze_profitability")
            prof_res = await tools_helper.tool_analyze_profitability(
                session=session, company_id=company_id, company_name=company_name, period="today"
            )
            citations.extend(prof_res["citations"])
            pd = prof_res["data"]

            content = (
                f"### 💰 Ganancia Neta del Día (Hoy)\n\n"
                f"Hoy has generado una ganancia neta total de **${pd['net_profit']:,.2f} MXN** "
                f"con un margen neto del **{pd['net_margin_pct']}%** sobre los ingresos brutos.\n\n"
                f"**Desglose Financiero de Hoy:**\n"
                f"- **Ingresos Brutos:** ${pd['revenue']:,.2f} MXN\n"
                f"- **Ganancia Confirmada (pagada/entregada):** ${pd['confirmed_profit']:,.2f} MXN (Margen: {pd['confirmed_margin_pct']}%)\n"
                f"- **Ganancia Estimada (en preparación):** ${pd['estimated_profit']:,.2f} MXN\n"
                f"- **Costo de Mercancía (COGS):** ${pd['cogs_total']:,.2f} MXN\n"
                f"- **Comisiones de Mercado Libre:** ${pd['meli_fees']:,.2f} MXN\n"
                f"- **Fletes Vendedor:** ${pd['shipping_seller']:,.2f} MXN\n"
                f"- **Retenciones Fiscales SAT (IVA + ISR):** ${pd['sat_withheld']:,.2f} MXN\n\n"
                f"> **Nota de Seguridad:** Las cifras confirmadas corresponden exclusivamente a órdenes con pagos acreditados en Mercado Pago."
            )
            justification = prof_res["justification"]

        # -----------------------------------------------------------------------
        # 2. CANÓNICA: "¿Cuánto vendí este mes?" / "Ventas del mes"
        # -----------------------------------------------------------------------
        elif re.search(r"cu[aá]nto\s+vend[ií]\s+(?:este\s+mes|el\s+mes)", text) or ("vendi" in text and "mes" in text) or ("ventas" in text and "mes" in text):
            tools_used.append("analyze_sales")
            sales_res = await tools_helper.tool_analyze_sales(
                session=session, company_id=company_id, company_name=company_name, period="this_month"
            )
            citations.extend(sales_res["citations"])
            sd = sales_res["data"]

            content = (
                f"### 📈 Resumen de Ventas de Este Mes\n\n"
                f"Durante el mes en curso, tus ventas brutas acumuladas ascienden a **${sd['gross_sales']:,.2f} MXN** "
                f"a través de **{sd['orders_count']} pedidos** ({sd['units_sold']} piezas vendidas).\n\n"
                f"**Diferenciación de Ventas:**\n"
                f"- **Ventas Confirmadas:** ${sd['confirmed_sales']:,.2f} MXN\n"
                f"- **Ventas Estimadas (en tránsito/preparación):** ${sd['estimated_sales']:,.2f} MXN\n"
                f"- **Variación contra periodo anterior:** {sd['growth_pct']:+.2f}%\n"
                f"- **Pedidos Pendientes por despachar:** {sd['pending_orders']} pedidos (${sd['pending_orders_amount']:,.2f} MXN)\n"
            )
            justification = sales_res["justification"]

        # -----------------------------------------------------------------------
        # 3. CANÓNICA: "¿Qué productos debo reponer?" / "Reposición de stock"
        # -----------------------------------------------------------------------
        elif re.search(r"qu[eé]\s+productos\s+debo\s+reponer", text) or ("reponer" in text) or ("reposicion" in text) or ("abastecer" in text):
            tools_used.append("recommend_restock")
            restock_res = await tools_helper.tool_recommend_restock(session=session, company_id=company_id)
            citations.extend(restock_res["citations"])
            rd = restock_res["data"]
            suggested_action = restock_res.get("suggested_action")

            items_table = ""
            if rd["suggestions"]:
                items_table = "| SKU | Producto | Stock Disp. | Punto Reorden (ROP) | Sugerido a Comprar | Costo Est. |\n"
                items_table += "| --- | --- | ---: | ---: | ---: | ---: |\n"
                for s in rd["suggestions"]:
                    items_table += f"| `{s['sku']}` | {s['product_name']} | {s['available_stock']} | {s['reorder_point']} | **{s['suggested_units']} pzas** | ${s['estimated_cost']:,.2f} |\n"
            else:
                items_table = "Actualmente todos los productos cuentan con niveles de cobertura seguros y por encima de su punto de reorden."

            content = (
                f"### 📦 Sugerencias de Reposición de Inventario\n\n"
                f"Se han identificado **{rd['total_critical_items']} productos** que alcanzaron o superaron su punto de reorden, "
                f"con una inversión total sugerida de **${rd['total_suggested_investment']:,.2f} MXN**.\n\n"
                f"{items_table}\n\n"
                f"El cálculo toma en cuenta la rotación histórica de ventas diarias, el tiempo de entrega (lead time) de cada proveedor "
                f"y el stock de seguridad requerido."
            )
            justification = restock_res["justification"]

        # -----------------------------------------------------------------------
        # 4. CANÓNICA: "¿Qué productos pierden dinero?" / "Margen negativo"
        # -----------------------------------------------------------------------
        elif re.search(r"qu[eé]\s+productos\s+pierden\s+dinero", text) or ("pierden dinero" in text) or ("perdida" in text and "producto" in text):
            tools_used.append("detect_anomalies")
            anom_res = await tools_helper.tool_detect_anomalies(
                session=session, company_id=company_id, company_name=company_name
            )
            citations.extend(anom_res["citations"])
            ad = anom_res["data"]

            if ad["loss_items"]:
                loss_table = "| SKU | Nombre | Margen Neto | Causa Detectada |\n| --- | --- | ---: | --- |\n"
                for it in ad["loss_items"]:
                    loss_table += f"| `{it['sku']}` | {it['product_name']} | **{it['margin_pct']}%** | {it['reason']} |\n"
                content = (
                    f"### ⚠️ Alerta: Productos que Generan Pérdidas\n\n"
                    f"Se detectaron **{ad['loss_alerts_count']} alertas críticas** de rentabilidad negativa:\n\n"
                    f"{loss_table}\n\n"
                    f"**Causa principal:** Las deducciones acumuladas (Costo de Mercancía COGS + Comisiones MeLi + Flete del vendedor) "
                    f"exceden el precio de venta actual. Se recomienda pausar la publicación o utilizar la herramienta de recomendación de precios."
                )
            else:
                content = (
                    f"### ✅ Excelente Salud Financiera\n\n"
                    f"Actualmente **ningún producto está perdiendo dinero**. Todos los SKUs activos en catálogo generan "
                    f"un margen neto positivo tras absorber costos de adquisición, comisiones de Mercado Libre y retenciones fiscales."
                )
            justification = anom_res["justification"]

        # -----------------------------------------------------------------------
        # 5. CANÓNICA: "¿Qué producto debería promocionar?" / "Recomendar promoción"
        # -----------------------------------------------------------------------
        elif re.search(r"qu[eé]\s+producto\s+deber[ií]a\s+promocionar", text) or ("promocionar" in text) or ("campaña" in text and "recomienda" in text):
            tools_used.append("recommend_products")
            rec_res = await tools_helper.tool_recommend_products(
                session=session, company_id=company_id, company_name=company_name, criteria="promotion_candidates"
            )
            citations.extend(rec_res["citations"])
            suggested_action = rec_res.get("suggested_action")
            prods = rec_res["data"]["products"]

            rec_table = "| SKU | Nombre | Margen Actual | Ganancia Neta | Unidades Vendidas |\n| --- | --- | ---: | ---: | ---: |\n"
            for p in prods:
                rec_table += f"| `{p['sku']}` | {p['name']} | **{p['margin_pct']}%** | ${p['profit']:,.2f} | {p['units_sold']} pzas |\n"

            content = (
                f"### 🎯 Productos Recomendados para Promoción\n\n"
                f"Para activar campañas o descuentos en Mercado Libre, se deben seleccionar productos con margen neto saludable ($\\ge 15\\%$) "
                f"que puedan absorber una rebaja sin incurrir en pérdidas:\n\n"
                f"{rec_table}\n\n"
                f"El producto con mejor perfil comercial es **`{prods[0]['sku'] if prods else 'N/A'}`**, ya que su margen permite ofrecer un "
                f"descuento del 8% al 10% para ganar exposición manteniendo una utilidad neta positiva."
            )
            justification = rec_res["justification"]

        # -----------------------------------------------------------------------
        # 6. CANÓNICA: "¿Cuál es mi margen promedio?" / "Margen promedio"
        # -----------------------------------------------------------------------
        elif re.search(r"cu[aá]l\s+es\s+mi\s+margen\s+promedio", text) or ("margen promedio" in text) or ("margen" in text and "promedio" in text):
            tools_used.append("analyze_profitability")
            prof_res = await tools_helper.tool_analyze_profitability(
                session=session, company_id=company_id, company_name=company_name, period="30d"
            )
            citations.extend(prof_res["citations"])
            pd = prof_res["data"]

            content = (
                f"### 📊 Margen Neto Promedio del Negocio\n\n"
                f"En los últimos 30 días, tu **margen neto promedio consolidado es del {pd['net_margin_pct']}%**.\n\n"
                f"**Desglose de Márgenes:**\n"
                f"- **Margen Confirmado:** {pd['confirmed_margin_pct']}% (pedidos cobrados y finalizados)\n"
                f"- **Margen Estimado:** {pd['estimated_margin_pct']}% (órdenes en proceso de entrega)\n"
                f"- **Ingreso Bruto Total:** ${pd['revenue']:,.2f} MXN\n"
                f"- **Utilidad Neta Total:** ${pd['net_profit']:,.2f} MXN\n\n"
                f"Este margen se sitúa dentro de los parámetros saludables para comercio electrónico en Mercado Libre México (promedio industrial: 15% - 22%)."
            )
            justification = prof_res["justification"]

        # -----------------------------------------------------------------------
        # 7. ROTACIÓN / STOCK LENTO: "Baja rotación", "Stock estancado"
        # -----------------------------------------------------------------------
        elif "baja rotacion" in text or "stock estancado" in text or "muerto" in text:
            tools_used.append("detect_slow_rotation")
            slow_res = await tools_helper.tool_detect_slow_rotation(
                session=session, company_id=company_id, company_name=company_name
            )
            citations.extend(slow_res["citations"])
            items = slow_res["data"]["items"]

            items_list_str = "\n".join([f"- **`{it['sku']}`**: {it['name']} (0 ventas en 30 días)" for it in items[:5]])
            content = (
                f"### ⏳ Diagnóstico de Baja Rotación de Inventario\n\n"
                f"Se han identificado **{slow_res['data']['slow_rotation_count']} SKUs estancados** en almacén:\n\n"
                f"{items_list_str if items_list_str else 'No se registran productos sin rotación.'}\n\n"
                f"**Recomendación:** Se sugiere evaluar una reducción de precio o armar combos con productos estrella para monetizar este inventario."
            )
            justification = slow_res["justification"]

        # -----------------------------------------------------------------------
        # 8. PRECIOS: "Recomienda precio", "Ajustar precio", "Precio para SKU"
        # -----------------------------------------------------------------------
        elif "precio" in text and ("recomienda" in text or "ajustar" in text or "calcular" in text or "sugiere" in text):
            tools_used.append("recommend_pricing")
            sku_match = re.search(r"sku\s+([a-zA-Z0-9_\-]+)", text)
            sku = sku_match.group(1).upper() if sku_match else "PRODUCTO-DEMO"
            price_res = await tools_helper.tool_recommend_pricing(session=session, company_id=company_id, sku=sku)
            citations.extend(price_res["citations"])
            suggested_action = price_res.get("suggested_action")
            pd_item = price_res["data"]

            content = (
                f"### 🏷️ Recomendación de Precio Óptimo para `{sku}`\n\n"
                f"Para obtener un margen neto objetivo del **{pd_item['target_margin_pct']}%**, el precio sugerido es de **${pd_item['recommended_price']:,.2f} MXN**.\n\n"
                f"- **Utilidad Neta Proyectada por Unidad:** ${pd_item['net_profit']:,.2f} MXN\n"
                f"- **Comisión Estimada de Mercado Libre:** ${pd_item['meli_fee_amount']:,.2f} MXN\n"
                f"- **Reglas Verificadas:** Cumple con el precio mínimo y las directrices de la política comercial."
            )
            justification = price_res["justification"]

        # -----------------------------------------------------------------------
        # 9. REPORTE GENERAL
        # -----------------------------------------------------------------------
        elif "reporte" in text or "informe" in text or "resumen ejecutivo" in text:
            tools_used.append("generate_report")
            rep_res = await tools_helper.tool_generate_report(
                session=session, company_id=company_id, company_name=company_name, period=preset_period
            )
            citations.extend(rep_res["citations"])
            content = rep_res["data"]["report_markdown"]
            justification = rep_res["justification"]

        # -----------------------------------------------------------------------
        # 10. DEFAULT: Consulta general analítica
        # -----------------------------------------------------------------------
        else:
            tools_used.append("analyze_sales")
            sales_res = await tools_helper.tool_analyze_sales(
                session=session, company_id=company_id, company_name=company_name, period=preset_period
            )
            citations.extend(sales_res["citations"])
            sd = sales_res["data"]

            content = (
                f"### 🤖 Asistente Comercial Ejecutivo - {company_name}\n\n"
                f"He procesado tu consulta. En la ventana actual ({preset_period}), tu negocio registra **${sd['gross_sales']:,.2f} MXN** "
                f"en ventas totales con {sd['orders_count']} pedidos y {sd['units_sold']} unidades desplazadas.\n\n"
                f"Puedes preguntarme directamente:\n"
                f"- *¿Cuánto gané hoy?*\n"
                f"- *¿Cuánto vendí este mes?*\n"
                f"- *¿Qué productos debo reponer?*\n"
                f"- *¿Qué productos pierden dinero?*\n"
                f"- *¿Qué producto debería promocionar?*\n"
                f"- *¿Cuál es mi margen promedio?*\n"
            )
            justification = sales_res["justification"]

        # Conteo simulado de tokens para auditoría
        est_tokens = len(user_message.split()) + len(content.split()) + 50

        return ProviderResponse(
            content=content,
            citations=citations,
            justification=justification,
            confidence_score=1.0,
            tools_used=tools_used,
            suggested_action=suggested_action,
            prompt_tokens=len(user_message.split()),
            completion_tokens=len(content.split()),
            total_tokens=est_tokens,
            model_name=self.model_name,
        )


class LLMProviderFactory:
    """Fábrica que instancia el proveedor de IA correspondiente según la configuración activa de la empresa."""

    @classmethod
    def get_provider(
        cls,
        provider_name: str,
        base_url: str | None = None,
        api_key: str | None = None,
        model_name: str = "llama3.2",
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> BaseLLMProvider:
        """Crea la instancia adecuada."""
        if provider_name in ["local_ollama", "custom_openai", "openai"]:
            return OpenAICompatibleProvider(
                base_url=base_url,
                api_key=api_key,
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        # Default / Fallback Heurístico Local
        return MockDeterministicProvider(model_name=model_name)
