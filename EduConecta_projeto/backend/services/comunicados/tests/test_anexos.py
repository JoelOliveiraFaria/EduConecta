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


def test_rota_de_video_em_comunicado_ja_nao_existe(client):
    """Vídeo deixou de ser um anexo de comunicado — passou para mensagens de
    chat (ver test_chat.py). Confirma que a rota antiga não existe mais."""
    resposta = client.post(
        f"/turmas/{TURMA_ID}/comunicados/{COMUNICADO_ID}/videos", json={}
    )
    assert resposta.status_code == 404

    resposta = client.get(
        f"/turmas/{TURMA_ID}/comunicados/{COMUNICADO_ID}/videos"
    )
    assert resposta.status_code == 404
