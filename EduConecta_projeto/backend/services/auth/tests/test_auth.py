from unittest.mock import AsyncMock

from bson import ObjectId
from werkzeug.security import generate_password_hash

import models.utilizador as modelo_utilizador
from utils.tokens import gerar_token


async def test_health(client):
    resposta = await client.get("/health")
    assert resposta.status_code == 200
    corpo = await resposta.get_json()
    assert corpo["status"] == "ok"


async def test_ready_quando_bd_ok(client, monkeypatch):
    monkeypatch.setattr(modelo_utilizador, "contar_colecoes", AsyncMock(return_value=[]))
    resposta = await client.get("/ready")
    assert resposta.status_code == 200


async def test_ready_quando_bd_falha(client, monkeypatch):
    from pymongo.errors import PyMongoError

    monkeypatch.setattr(
        modelo_utilizador, "contar_colecoes", AsyncMock(side_effect=PyMongoError())
    )
    resposta = await client.get("/ready")
    assert resposta.status_code == 503


async def test_registo_esta_bloqueado(client):
    resposta = await client.post(
        "/registo",
        json={"nome": "Ana Silva", "email": "ana@example.com", "password": "palavra-passe-longa"},
    )
    assert resposta.status_code == 403
    corpo = await resposta.get_json()
    assert corpo["error"] == "registration_disabled"


async def test_login_sem_json(client):
    resposta = await client.post("/login", data="nao-e-json")
    assert resposta.status_code == 415


async def test_login_campos_invalidos(client):
    resposta = await client.post("/login", json={"email": "ana@example.com"})
    assert resposta.status_code == 400


async def test_login_credenciais_invalidas(client, monkeypatch):
    monkeypatch.setattr(modelo_utilizador, "obter_por_email", AsyncMock(return_value=None))
    resposta = await client.post(
        "/login", json={"email": "ninguem@example.com", "password": "palavra-passe-errada"}
    )
    assert resposta.status_code == 401


async def test_login_sucesso(client, monkeypatch):
    utilizador = {
        "_id": ObjectId(),
        "nome": "Ana Silva",
        "email": "ana@example.com",
        "perfil": "encarregado",
        "estado": "ativo",
        "password_hash": generate_password_hash("palavra-passe-correta", method="scrypt"),
    }
    monkeypatch.setattr(modelo_utilizador, "obter_por_email", AsyncMock(return_value=utilizador))

    resposta = await client.post(
        "/login", json={"email": "ana@example.com", "password": "palavra-passe-correta"}
    )

    assert resposta.status_code == 200
    corpo = await resposta.get_json()
    assert corpo["utilizador"]["email"] == "ana@example.com"
    assert "access_token" in corpo


async def test_me_sem_token(client):
    resposta = await client.get("/me")
    assert resposta.status_code == 401


async def test_me_com_token_valido(client, monkeypatch):
    utilizador_id = ObjectId()
    utilizador = {
        "_id": utilizador_id,
        "nome": "Ana Silva",
        "email": "ana@example.com",
        "perfil": "encarregado",
        "estado": "ativo",
        "deve_alterar_password": False,
    }
    monkeypatch.setattr(modelo_utilizador, "obter_por_id", AsyncMock(return_value=utilizador))

    token = gerar_token(utilizador_id)
    resposta = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert resposta.status_code == 200
    corpo = await resposta.get_json()
    assert corpo["id"] == str(utilizador_id)
