from unittest.mock import MagicMock

from bson import ObjectId
from flask import g

import controllers.anexo_controller as anexo_controller

TURMA_ID = str(ObjectId())
COMUNICADO_ID = str(ObjectId())


def _acesso_concedido(turma_id, publicar=False):
    g.turma_id = str(ObjectId(turma_id))
    g.utilizador_id = str(ObjectId())
    return None


def test_listar_fotos_comunicado_inexistente(client, monkeypatch):
    monkeypatch.setattr(anexo_controller, "verificar_acesso", _acesso_concedido)
    monkeypatch.setattr(
        "models.comunicado.obter_acessivel", MagicMock(return_value=None)
    )

    resposta = client.get(f"/turmas/{TURMA_ID}/comunicados/{COMUNICADO_ID}/fotografias")

    assert resposta.status_code == 404


def test_obter_foto_id_invalido(client, monkeypatch):
    monkeypatch.setattr(anexo_controller, "verificar_acesso", _acesso_concedido)
    monkeypatch.setattr(
        "models.comunicado.obter_acessivel", MagicMock(return_value={"_id": ObjectId()})
    )

    resposta = client.get(
        f"/turmas/{TURMA_ID}/comunicados/{COMUNICADO_ID}/fotografias/nao-e-objectid"
    )

    assert resposta.status_code == 400


def test_carregar_video_sem_multipart(client, monkeypatch):
    monkeypatch.setattr(anexo_controller, "verificar_acesso", _acesso_concedido)
    monkeypatch.setattr(
        "models.comunicado.obter_editavel", MagicMock(return_value={"_id": ObjectId()})
    )

    resposta = client.post(
        f"/turmas/{TURMA_ID}/comunicados/{COMUNICADO_ID}/videos", json={}
    )

    assert resposta.status_code == 415
