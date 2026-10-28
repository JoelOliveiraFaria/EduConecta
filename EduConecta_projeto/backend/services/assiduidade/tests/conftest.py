import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_ASSIDUIDADE_DATABASE", "assiduidade_test")

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
def conta_docente(monkeypatch):
    conta = {"id": "6ae24e41252e5bf6b58984ab", "estado": "ativo", "perfil": "docente"}
    monkeypatch.setattr("app.consultar", lambda url: (conta, None))
    return conta


@pytest.fixture
def conta_encarregado(monkeypatch):
    conta = {"id": "6ae24e41252e5bf6b58984ab", "estado": "ativo", "perfil": "encarregado"}
    monkeypatch.setattr("app.consultar", lambda url: (conta, None))
    return conta
