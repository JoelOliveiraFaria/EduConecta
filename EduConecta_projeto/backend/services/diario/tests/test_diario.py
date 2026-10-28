from datetime import datetime, timezone
from unittest.mock import MagicMock

import models.registo as modelo_registo


def _documento(**overrides):
    base = {
        "_id": "aluno1:2026-01-10",
        "aluno_id": "aluno1",
        "turma_id": "turma1",
        "data": "2026-01-10",
        "alimentacao": "Comeu bem",
        "sono": "Dormiu a sesta",
        "higiene": "",
        "atividades": "",
        "observacoes": "",
        "criado_por": "prof1",
        "criado_em": datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


def test_health(client):
    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.get_json()["status"] == "ok"


def test_ready_quando_bd_ok(client, monkeypatch):
    monkeypatch.setattr(modelo_registo, "contar_colecoes", lambda: [])
    resposta = client.get("/ready")
    assert resposta.status_code == 200


def test_ready_quando_bd_falha(client, monkeypatch):
    from pymongo.errors import PyMongoError

    def falhar():
        raise PyMongoError()

    monkeypatch.setattr(modelo_registo, "contar_colecoes", falhar)
    resposta = client.get("/ready")
    assert resposta.status_code == 503


def test_criar_registo_campos_invalidos(client, monkeypatch):
    monkeypatch.setattr("controllers.diario_controller.verificar_acesso", lambda t, a: None)

    resposta = client.post(
        "/turmas/t1/alunos/a1/diario",
        json={"data": "2026-01-10"},
    )
    assert resposta.status_code == 400


def test_criar_registo_sucesso(client, monkeypatch):
    monkeypatch.setattr(modelo_registo, "inserir", MagicMock(return_value=None))

    import controllers.diario_controller as controller

    def fake_verificar(turma_id, aluno_id):
        from flask import g

        g.utilizador_id = "prof1"
        return None

    monkeypatch.setattr(controller, "verificar_acesso", fake_verificar)

    resposta = client.post(
        "/turmas/686f6f6f6f6f6f6f6f6f6f6f/alunos/686f6f6f6f6f6f6f6f6f6f6e/diario",
        json={
            "data": "2026-01-10",
            "alimentacao": "Comeu bem",
            "sono": "",
            "higiene": "",
            "atividades": "",
            "observacoes": "",
        },
    )

    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["data"] == "2026-01-10"
    assert corpo["alimentacao"] == "Comeu bem"


def test_listar_registos(client, monkeypatch):
    import controllers.diario_controller as controller

    monkeypatch.setattr(controller, "verificar_acesso", lambda t, a: None)
    monkeypatch.setattr(
        modelo_registo, "listar_por_aluno_turma", lambda a, t, limite=31: [_documento()]
    )

    resposta = client.get(
        "/turmas/686f6f6f6f6f6f6f6f6f6f6f/alunos/686f6f6f6f6f6f6f6f6f6f6e/diario"
    )

    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["quantidade"] == 1
    assert corpo["registos"][0]["aluno_id"] == "aluno1"


def test_editar_registo_nao_encontrado(client, monkeypatch):
    import controllers.diario_controller as controller

    def fake_verificar(turma_id, aluno_id):
        from flask import g

        g.utilizador_id = "prof1"
        return None

    monkeypatch.setattr(controller, "verificar_acesso", fake_verificar)
    monkeypatch.setattr(modelo_registo, "atualizar", lambda *a, **k: None)

    resposta = client.patch(
        "/turmas/686f6f6f6f6f6f6f6f6f6f6f/alunos/686f6f6f6f6f6f6f6f6f6f6e/diario/2026-01-10",
        json={"observacoes": "Nova nota"},
    )

    assert resposta.status_code == 404
