import os

os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_AUTH_DATABASE", "auth_test")
os.environ.setdefault("JWT_SECRET_KEY", "x" * 32)

import pytest

from app import app as quart_app


@pytest.fixture
def app():
    quart_app.config["TESTING"] = True
    return quart_app


@pytest.fixture
def client(app):
    return app.test_client()
