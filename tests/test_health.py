"""Pruebas del endpoint de salud y diagnóstico del sistema."""


def test_root_endpoint(client):
    """Comprueba que la raíz responda con el estado del API."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["name"] == "ERP Mercado Libre México API"
    assert "X-Request-ID" in response.headers


def test_health_check_endpoint(client):
    """Comprueba que el endpoint de salud responda correctamente con diagnósticos."""
    response = client.get("/api/v1/health")
    assert response.status_code in [200, 503]
    data = response.json()
    assert "status" in data
    assert "checks" in data
    assert "database" in data["checks"]
    assert "redis" in data["checks"]
    assert "storage" in data["checks"]
    assert data["checks"]["storage"]["status"] == "up"
