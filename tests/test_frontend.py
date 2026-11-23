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


def test_frontend_js_import_graph_resolves():
    """Regresión: cada import nombrado del frontend debe existir como export
    en su módulo destino. Un import roto tumba todo el grafo de módulos ES y
    la SPA queda en blanco (pasó con renderLogin/renderDashboard/renderOrders/
    renderInventory/renderWarehouses, initSearchModal y openProfileModal)."""
    import posixpath
    import re
    from pathlib import Path

    js_root = Path(__file__).resolve().parent.parent / "src" / "static" / "js"

    def exports_of(path: Path) -> set:
        src = path.read_text(encoding="utf-8")
        names = set(re.findall(r"^export (?:async )?function (\w+)", src, re.M))
        names |= set(re.findall(r"^export (?:const|let|var|class) (\w+)", src, re.M))
        for block in re.findall(r"export\s*\{([^}]*)\}", src):
            for part in block.split(","):
                part = part.strip()
                if part:
                    names.add(part.split(" as ")[-1].strip())
        return names

    files = {
        str(p.relative_to(js_root)): exports_of(p) for p in js_root.rglob("*.js")
    }
    assert files, "no se encontraron archivos JS del frontend"

    broken = []
    for path in js_root.rglob("*.js"):
        rel = str(path.relative_to(js_root))
        for match in re.finditer(
            r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]",
            path.read_text(encoding="utf-8"),
        ):
            names = [
                n.strip().split(" as ")[0].strip()
                for n in match.group(1).split(",")
                if n.strip()
            ]
            target = posixpath.normpath(
                posixpath.join(posixpath.dirname(rel), match.group(2))
            )
            if target not in files:
                broken.append(f"{rel} importa de un archivo inexistente: {match.group(2)}")
                continue
            for name in names:
                if name not in files[target]:
                    broken.append(
                        f"{rel} importa '{name}' de {match.group(2)}, "
                        f"pero ese módulo solo exporta {sorted(files[target])}"
                    )
    assert not broken, "imports nombrados rotos en el frontend:\n" + "\n".join(broken)
