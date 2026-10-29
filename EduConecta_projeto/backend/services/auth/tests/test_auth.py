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


def _mock_admin(monkeypatch, admin_id, extra_lookup=None):
    """Prepara obter_por_id para devolver um admin válido para o id do token,
    e opcionalmente outro valor para um segundo id consultado (extra_lookup)."""
    admin_doc = {
        "_id": admin_id,
        "perfil": "admin",
        "estado": "ativo",
        "deve_alterar_password": False,
    }

    async def fake_obter_por_id(utilizador_id, projecao=None):
        if str(utilizador_id) == str(admin_id):
            return admin_doc
        if extra_lookup is not None:
            return extra_lookup
        return None

    monkeypatch.setattr(modelo_utilizador, "obter_por_id", AsyncMock(side_effect=fake_obter_por_id))
    return gerar_token(admin_id)


async def test_admin_route_sem_admin_e_rejeitada(client, monkeypatch):
    conta_id = ObjectId()
    nao_admin = {
        "_id": conta_id,
        "perfil": "encarregado",
        "estado": "ativo",
        "deve_alterar_password": False,
    }
    monkeypatch.setattr(modelo_utilizador, "obter_por_id", AsyncMock(return_value=nao_admin))
    token = gerar_token(conta_id)

    resposta = await client.patch(
        f"/admin/utilizadores/{ObjectId()}",
        headers={"Authorization": f"Bearer {token}"},
        json={"nome": "Novo Nome"},
    )

    assert resposta.status_code == 403
    corpo = await resposta.get_json()
    assert corpo["error"] == "forbidden"


async def test_editar_utilizador_sucesso(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "ativo"})
    monkeypatch.setattr(modelo_utilizador, "existe_email", AsyncMock(return_value=None))
    monkeypatch.setattr(
        modelo_utilizador,
        "atualizar_dados",
        AsyncMock(return_value={
            "_id": alvo_id, "nome": "Novo Nome", "email": "novo@example.com",
            "perfil": "docente", "estado": "ativo",
        }),
    )

    resposta = await client.patch(
        f"/admin/utilizadores/{alvo_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"nome": "Novo Nome", "email": "novo@example.com", "perfil": "docente"},
    )

    assert resposta.status_code == 200
    corpo = await resposta.get_json()
    assert corpo["nome"] == "Novo Nome"
    assert corpo["perfil"] == "docente"


async def test_editar_utilizador_sem_campos(client, monkeypatch):
    admin_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id)

    resposta = await client.patch(
        f"/admin/utilizadores/{ObjectId()}",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )

    assert resposta.status_code == 400


async def test_editar_utilizador_email_duplicado(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "ativo"})
    monkeypatch.setattr(modelo_utilizador, "existe_email", AsyncMock(return_value={"_id": ObjectId()}))

    resposta = await client.patch(
        f"/admin/utilizadores/{alvo_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "ocupado@example.com"},
    )

    assert resposta.status_code == 409


async def test_editar_utilizador_eliminado_da_404(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "eliminado"})

    resposta = await client.patch(
        f"/admin/utilizadores/{alvo_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"nome": "Novo Nome"},
    )

    assert resposta.status_code == 404


async def test_desativar_utilizador_sucesso(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "ativo"})
    monkeypatch.setattr(
        modelo_utilizador, "desativar", AsyncMock(return_value={"_id": alvo_id, "estado": "inativo"})
    )

    resposta = await client.post(
        f"/admin/utilizadores/{alvo_id}/desativar", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 200
    corpo = await resposta.get_json()
    assert corpo["estado"] == "inativo"


async def test_desativar_a_propria_conta_e_bloqueado(client, monkeypatch):
    admin_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id)

    resposta = await client.post(
        f"/admin/utilizadores/{admin_id}/desativar", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 403
    corpo = await resposta.get_json()
    assert corpo["error"] == "cannot_act_on_self"


async def test_desativar_conta_ja_inativa_da_409(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "inativo"})

    resposta = await client.post(
        f"/admin/utilizadores/{alvo_id}/desativar", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 409


async def test_reativar_utilizador_sucesso(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "inativo"})
    monkeypatch.setattr(
        modelo_utilizador, "reativar", AsyncMock(return_value={"_id": alvo_id, "estado": "ativo"})
    )

    resposta = await client.post(
        f"/admin/utilizadores/{alvo_id}/reativar", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 200
    corpo = await resposta.get_json()
    assert corpo["estado"] == "ativo"


async def test_reativar_conta_eliminada_e_bloqueado(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "eliminado"})

    resposta = await client.post(
        f"/admin/utilizadores/{alvo_id}/reativar", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 409


async def test_eliminar_utilizador_sucesso(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "ativo"})
    monkeypatch.setattr(
        modelo_utilizador, "eliminar", AsyncMock(return_value={"_id": alvo_id, "estado": "eliminado"})
    )

    resposta = await client.delete(
        f"/admin/utilizadores/{alvo_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 200
    corpo = await resposta.get_json()
    assert corpo["estado"] == "eliminado"


async def test_eliminar_a_propria_conta_e_bloqueado(client, monkeypatch):
    admin_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id)

    resposta = await client.delete(
        f"/admin/utilizadores/{admin_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 403
    corpo = await resposta.get_json()
    assert corpo["error"] == "cannot_act_on_self"


async def test_eliminar_utilizador_ja_eliminado_da_404(client, monkeypatch):
    admin_id = ObjectId()
    alvo_id = ObjectId()
    token = _mock_admin(monkeypatch, admin_id, extra_lookup={"_id": alvo_id, "estado": "eliminado"})

    resposta = await client.delete(
        f"/admin/utilizadores/{alvo_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert resposta.status_code == 404
