from unittest.mock import MagicMock

import controllers.chat_controller as chat_controller


def _conta_docente(perfil="docente"):
    return {"id": "6" * 24, "estado": "ativo", "perfil": perfil}, None


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
