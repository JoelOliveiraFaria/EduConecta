from unittest.mock import MagicMock

from pymongo.errors import PyMongoError


def test_health(client):
    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.get_json()["status"] == "ok"


def test_ready_ok(client, monkeypatch):
    import controllers.health_controller as health_controller

    monkeypatch.setattr(health_controller.database, "list_collection_names", MagicMock(return_value=[]))
    resposta = client.get("/ready")
    assert resposta.status_code == 200


def test_ready_falha(client, monkeypatch):
    import controllers.health_controller as health_controller

    monkeypatch.setattr(
        health_controller.database,
        "list_collection_names",
        MagicMock(side_effect=PyMongoError()),
    )
    resposta = client.get("/ready")
    assert resposta.status_code == 503
