import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_NOTIFICACOES_DATABASE", "notificacoes_test")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("INTERNAL_SERVICE_KEY", "chave-de-teste")
os.environ["DISABLE_RABBITMQ_CONSUMER"] = "true"

import pytest

from app import app as flask_app


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def conta(monkeypatch):
    conta = {"id": "6ae24e41252e5bf6b58984ab", "estado": "ativo", "perfil": "encarregado"}
    monkeypatch.setattr("app.consultar", lambda url: (conta, None))
    return conta
