"""Pruebas de entrega del frontend SPA y montado de archivos estáticos."""

from starlette.testclient import TestClient
from src.main import app


def test_frontend_spa_serving():
    """Comprueba que /app sirva la SPA correctamente."""
    with TestClient(app) as client:
        response = client.get("/app")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "ERP Mercado Libre México" in response.text
        assert "app-root" in response.text


def test_static_assets_serving():
    """Comprueba que los archivos CSS y JS estáticos se sirvan con código 200."""
    with TestClient(app) as client:
        css_res = client.get("/static/css/styles.css")
        assert css_res.status_code == 200
        assert "text/css" in css_res.headers["content-type"]

        js_res = client.get("/static/js/app.js")
        assert js_res.status_code == 200


def test_root_content_negotiation():
    """Comprueba que / devuelva JSON para APIs y HTML para navegadores web."""
    with TestClient(app) as client:
        # Request normal de API / TestClient
        api_res = client.get("/")
        assert api_res.status_code == 200
        data = api_res.json()
        assert data["name"] == "ERP Mercado Libre México API"

        # Request de navegador con Accept: text/html
        browser_res = client.get("/", headers={"accept": "text/html"})
        assert browser_res.status_code == 200
        assert "text/html" in browser_res.headers["content-type"]
        assert "<!DOCTYPE html>" in browser_res.text
