import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_ESCOLAR_DATABASE", "escolar_test")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
os.environ.setdefault("INTERNAL_SERVICE_KEY", "chave-de-teste")

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
def autenticar(monkeypatch):
    """Faz `verificar_acesso_escolar` aceitar qualquer pedido como o utilizador dado."""

    def _aplicar(utilizador):
        import controllers.blueprint as blueprint_module

        monkeypatch.setattr(
            blueprint_module,
            "obter_utilizador_da_sessao",
            lambda token: (utilizador, None),
        )

    return _aplicar
