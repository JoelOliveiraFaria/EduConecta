from datetime import datetime, timezone
from unittest.mock import MagicMock

from bson import ObjectId
from flask import g

import controllers.comunicado_controller as comunicado_controller
import models.comunicado as modelo_comunicado

TURMA_ID = str(ObjectId())


def _acesso_concedido(turma_id, publicar=False):
    g.turma_id = str(ObjectId(turma_id))
    g.utilizador_id = str(ObjectId())
    return None


def test_publicar_sem_json(client, monkeypatch):
    monkeypatch.setattr(comunicado_controller, "verificar_acesso", _acesso_concedido)
    resposta = client.post(f"/turmas/{TURMA_ID}/comunicados", data="nao-e-json")
    assert resposta.status_code == 415


def test_publicar_campos_invalidos(client, monkeypatch):
    monkeypatch.setattr(comunicado_controller, "verificar_acesso", _acesso_concedido)
    resposta = client.post(f"/turmas/{TURMA_ID}/comunicados", json={"titulo": "Só título"})
    assert resposta.status_code == 400


def test_publicar_sucesso(client, monkeypatch):
    monkeypatch.setattr(comunicado_controller, "verificar_acesso", _acesso_concedido)

    documento = {
        "_id": ObjectId(),
        "turma_id": TURMA_ID,
        "titulo": "Reunião",
        "texto": "Marcada para sexta-feira.",
        "criado_em": datetime.now(timezone.utc),
    }
    monkeypatch.setattr(modelo_comunicado, "criar", MagicMock(return_value=documento))

    resposta = client.post(
        f"/turmas/{TURMA_ID}/comunicados",
        json={"titulo": "Reunião", "texto": "Marcada para sexta-feira."},
    )

    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["titulo"] == "Reunião"


def test_listar_query_invalida(client, monkeypatch):
    monkeypatch.setattr(comunicado_controller, "verificar_acesso", _acesso_concedido)
    resposta = client.get(f"/turmas/{TURMA_ID}/comunicados?pagina=1&outro=2")
    assert resposta.status_code == 400


def test_listar_sucesso(client, monkeypatch):
    monkeypatch.setattr(comunicado_controller, "verificar_acesso", _acesso_concedido)
    monkeypatch.setattr(modelo_comunicado, "listar_por_turma", MagicMock(return_value=[]))

    resposta = client.get(f"/turmas/{TURMA_ID}/comunicados")

    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["comunicados"] == []
    assert resposta.headers["Cache-Control"] == "no-store"
