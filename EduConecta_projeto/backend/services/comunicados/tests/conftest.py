import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_COMUNICADOS_DATABASE", "comunicados_test")
os.environ.setdefault("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

import pytest

from app import app as flask_app


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()
