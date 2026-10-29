from datetime import datetime, timezone
from unittest.mock import MagicMock

from bson import ObjectId

import controllers.chat_controller as chat_controller

CONVERSA_ID = "a" * 64


def _conta_docente(perfil="docente"):
    return {"id": "6" * 24, "estado": "ativo", "perfil": perfil}, None


def _conversa_autorizada():
    conversa = {"_id": CONVERSA_ID}
    conta = {"id": "6" * 24, "estado": "ativo", "perfil": "docente"}
    return conversa, conta, None


def _mensagem_doc(tipo, **extra):
    base = {
        "_id": ObjectId(),
        "conversa_id": CONVERSA_ID,
        "tipo": tipo,
        "texto": None,
        "anexo_id": None,
        "enviado_por": "6" * 24,
        "criado_em": datetime.now(timezone.utc),
    }
    base.update(extra)
    return base


def test_criar_conversa_sem_json(client, monkeypatch):
    monkeypatch.setattr(chat_controller, "obter_conta_chat", lambda: _conta_docente())
    resposta = client.post("/conversas", data="nao-e-json")
    assert resposta.status_code == 415


def test_criar_conversa_campos_invalidos(client, monkeypatch):
    monkeypatch.setattr(chat_controller, "obter_conta_chat", lambda: _conta_docente())
    resposta = client.post("/conversas", json={"aluno_id": "invalido"})
    assert resposta.status_code == 400


def test_listar_conversas_cursor_invalido(client, monkeypatch):
    monkeypatch.setattr(chat_controller, "obter_conta_chat", lambda: _conta_docente())
    resposta = client.get("/conversas?depois_de=curto")
    assert resposta.status_code == 400


def test_enviar_mensagem_conversa_invalida(client, monkeypatch):
    monkeypatch.setattr(
        chat_controller,
        "obter_conversa_autorizada",
        MagicMock(return_value=(None, None, ({"error": "x"}, 404))),
    )
    resposta = client.post("/conversas/id-invalido/mensagens", json={"texto": "Olá"})
    assert resposta.status_code == 404


def test_enviar_mensagem_texto_sucesso(client, monkeypatch):
    monkeypatch.setattr(
        chat_controller, "obter_conversa_autorizada", MagicMock(return_value=_conversa_autorizada())
    )
    monkeypatch.setattr(
        "models.conversa.criar_mensagem",
        MagicMock(return_value=_mensagem_doc("texto", texto="Olá")),
    )

    resposta = client.post(f"/conversas/{CONVERSA_ID}/mensagens", json={"texto": "Olá"})

    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["tipo"] == "texto"
    assert corpo["texto"] == "Olá"
    assert corpo["anexo"] is None


# --- mensagens de fotografia/vídeo ------------------------------------------

def test_enviar_fotografia_sem_multipart(client, monkeypatch):
    monkeypatch.setattr(
        chat_controller, "obter_conversa_autorizada", MagicMock(return_value=_conversa_autorizada())
    )
    resposta = client.post(f"/conversas/{CONVERSA_ID}/mensagens/fotografia", json={})
    assert resposta.status_code == 415


def test_enviar_fotografia_sucesso(client, monkeypatch):
    monkeypatch.setattr(
        chat_controller, "obter_conversa_autorizada", MagicMock(return_value=_conversa_autorizada())
    )
    monkeypatch.setattr(
        chat_controller, "preparar_fotografia", lambda conteudo: (b"jpeg-bytes", 10, 10)
    )
    monkeypatch.setattr("models.anexo.guardar_fotografia_mensagem", MagicMock())
    anexo_id = ObjectId()
    monkeypatch.setattr(
        "models.conversa.criar_mensagem",
        MagicMock(return_value=_mensagem_doc("fotografia", anexo_id=anexo_id)),
    )

    resposta = client.post(
        f"/conversas/{CONVERSA_ID}/mensagens/fotografia",
        data={"fotografia": (__import__("io").BytesIO(b"conteudo-fake"), "foto.jpg")},
        content_type="multipart/form-data",
    )

    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["tipo"] == "fotografia"
    assert corpo["anexo"]["tipo"] == "image/jpeg"
    assert corpo["anexo"]["url"].endswith("/anexo")


def test_enviar_video_sem_multipart(client, monkeypatch):
    monkeypatch.setattr(
        chat_controller, "obter_conversa_autorizada", MagicMock(return_value=_conversa_autorizada())
    )
    resposta = client.post(f"/conversas/{CONVERSA_ID}/mensagens/video", json={})
    assert resposta.status_code == 415


def test_enviar_video_campo_errado(client, monkeypatch):
    monkeypatch.setattr(
        chat_controller, "obter_conversa_autorizada", MagicMock(return_value=_conversa_autorizada())
    )
    resposta = client.post(
        f"/conversas/{CONVERSA_ID}/mensagens/video",
        data={"ficheiro": (__import__("io").BytesIO(b"x"), "v.mp4")},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 400


def test_obter_anexo_mensagem_sem_anexo(client, monkeypatch):
    monkeypatch.setattr(
        chat_controller, "obter_conversa_autorizada", MagicMock(return_value=_conversa_autorizada())
    )
    monkeypatch.setattr(
        "models.conversa.obter_mensagem",
        MagicMock(return_value=_mensagem_doc("texto", texto="sem anexo")),
    )

    resposta = client.get(f"/conversas/{CONVERSA_ID}/mensagens/{ObjectId()}/anexo")

    assert resposta.status_code == 404


def test_obter_anexo_mensagem_nao_encontrada(client, monkeypatch):
    monkeypatch.setattr(
        chat_controller, "obter_conversa_autorizada", MagicMock(return_value=_conversa_autorizada())
    )
    monkeypatch.setattr("models.conversa.obter_mensagem", MagicMock(return_value=None))

    resposta = client.get(f"/conversas/{CONVERSA_ID}/mensagens/{ObjectId()}/anexo")

    assert resposta.status_code == 404
