"""Pruebas de ingesta y validación de Webhooks oficiales de Mercado Libre México."""


def test_meli_webhook_valid_order_payload(client):
    """Verifica que un payload oficial de orden sea recibido y aceptado inmediatamente."""
    payload = {
        "resource": "/orders/2000003456789",
        "user_id": 987654321,
        "topic": "orders_v2",
        "application_id": 12345678,
        "attempts": 1,
        "sent": "2026-11-17T23:30:00Z",
    }
    response = client.post("/api/v1/webhooks/meli", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["received", "accepted_with_warning"]
    assert data.get("topic") == "orders_v2"


def test_meli_webhook_invalid_payload_rejected(client):
    """Verifica que payloads corruptos o sin campos obligatorios sean rechazados con 422."""
    corrupted_payload = {
        "resource": "/orders/123",
        # Falta user_id, topic y application_id
    }
    response = client.post("/api/v1/webhooks/meli", json=corrupted_payload)
    assert response.status_code == 422
