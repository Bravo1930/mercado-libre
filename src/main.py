"""Punto de entrada principal de la aplicación FastAPI del ERP."""

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.v1 import api_v1_router
from src.core.config import get_settings
from src.core.database import check_database_connection, close_database_connections
from src.core.exceptions import AppException
from src.core.logging import get_logger, setup_logging
from src.core.redis import check_redis_connection, close_redis_connection
from src.core.security_headers import SecurityHeadersMiddleware
from src.core.rate_limiter import RateLimitMiddleware
from src.core.metrics import metrics_registry, metrics_endpoint

# Inicializar sistema de logs
setup_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida de la aplicación: inicialización y apagado controlado."""
    import os
    settings = get_settings()

    # Omitir chequeos de red si se encuentra en entorno de pruebas
    if os.environ.get("ENVIRONMENT") in ["testing", "test"]:
        yield
        return

    logger.info(
        f"Iniciando ERP Mercado Libre México v0.1.0 "
        f"[Entorno={settings.ENVIRONMENT}, Nodo={settings.NODE_NAME}]"
    )

    db_ok, db_msg = await check_database_connection()
    logger.info(f"Diagnóstico PostgreSQL al arranque: {db_msg}")
    metrics_registry.set_gauge("erp_database_connected", 1.0 if db_ok else 0.0)

    redis_ok, redis_msg = await check_redis_connection()
    logger.info(f"Diagnóstico Redis al arranque: {redis_msg}")
    metrics_registry.set_gauge("erp_redis_connected", 1.0 if redis_ok else 0.0)

    yield

    logger.info("Apagando servicios del ERP y liberando recursos...")
    await close_database_connections()
    await close_redis_connection()
    logger.info("ERP detenido correctamente.")


def create_app() -> FastAPI:
    """Fábrica de la aplicación FastAPI con manejo centralizado de excepciones."""
    settings = get_settings()

    app = FastAPI(
        title="ERP Inteligente Mercado Libre México",
        description=(
            "Plataforma ERP y SaaS para la administración integral de inventarios, "
            "ventas, publicaciones, guías de envío, compras y rentabilidad neta en Mercado Libre México."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    )

    # Middleware de Encabezados de Seguridad (CSP, HSTS, X-Frame-Options, X-Content-Type-Options)
    app.add_middleware(SecurityHeadersMiddleware)

    # Middleware de Control de Tasa (Rate Limiting y Prevención de Fuerza Bruta / Abuso de API)
    app.add_middleware(RateLimitMiddleware)

    # Middleware CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.ENVIRONMENT == "development" else [f"https://{settings.DOMAIN_NAME}"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Middleware de Trazabilidad (Request ID y Tiempo de Respuesta)
    @app.middleware("http")
    async def request_tracing_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.time()

        try:
            response: Response = await call_next(request)
            duration_sec = time.time() - start_time
            process_time = round(duration_sec * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time-Ms"] = str(process_time)

            metrics_registry.record_http_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_seconds=duration_sec
            )

            if request.url.path not in ["/api/v1/health"]:
                logger.info(
                    f"{request.method} {request.url.path} - "
                    f"Status={response.status_code} - Latency={process_time}ms [ReqID={request_id}]"
                )
            return response
        except Exception as exc:
            process_time = round((time.time() - start_time) * 1000, 2)
            logger.error(f"Error no controlado en {request.method} {request.url.path}: {exc} [ReqID={request_id}]")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Error interno del servidor",
                    "code": "INTERNAL_SERVER_ERROR",
                    "request_id": request_id,
                    "detail": str(exc) if settings.ENVIRONMENT != "production" else "Ocurrió un error inesperado.",
                },
                headers={"X-Request-ID": request_id},
            )

    # --------------------------------------------------------------------------
    # MANEJADORES CENTRALIZADOS DE EXCEPCIONES
    # --------------------------------------------------------------------------
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.message,
                "detail": exc.message,
                "code": exc.code,
                "details": exc.details,
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        errors = [
            {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": "Error de validación en los datos de entrada.",
                "code": "VALIDATION_ERROR",
                "details": {"validation_errors": errors},
                "request_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    # Inclusión de Rutas
    app.include_router(api_v1_router)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # Endpoint de Métricas Prometheus
    app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], tags=["Monitoreo"], include_in_schema=False)

    @app.get("/app", tags=["Frontend SPA"], response_class=FileResponse)
    @app.get("/app/{full_path:path}", tags=["Frontend SPA"], response_class=FileResponse)
    async def serve_spa(full_path: str = ""):
        """Sirve la aplicación de interfaz de usuario del ERP."""
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse(status_code=404, content={"error": "Frontend no disponible"})

    @app.get("/", tags=["Root"])
    async def root(request: Request):
        accept_header = request.headers.get("accept", "")
        index_file = static_dir / "index.html"
        if "text/html" in accept_header and "*/*" not in accept_header and index_file.exists():
            return FileResponse(str(index_file))
        return {
            "name": "ERP Mercado Libre México API",
            "version": "0.1.0",
            "status": "online",
            "docs": "/docs" if settings.ENVIRONMENT != "production" else "disabled_in_production",
            "health": "/api/v1/health",
        }

    return app


app = create_app()
