"""Testes: GET /me/notificacoes e PATCH /me/notificacoes/<id>/lida (Fase 2)."""

from datetime import datetime, timezone

from bson import ObjectId

AUTH_HEADER = {"Authorization": "Bearer qualquer-coisa"}


def _doc(**extra):
    base = {
        "_id": ObjectId(),
        "destinatario_utilizador_id": "6ae24e41252e5bf6b58984ab",
        "tipo": "comunicado",
        "titulo": "Novo comunicado",
        "mensagem": 'Foi publicado um novo comunicado: "Reunião".',
        "referencia": {"turma_id": str(ObjectId())},
        "lida": False,
        "criada_em": datetime.now(timezone.utc),
    }
    base.update(extra)
    return base


def test_listar_sem_auth_bloqueado(client):
    resposta = client.get("/me/notificacoes")
    assert resposta.status_code == 401


def test_listar_sucesso(client, conta, monkeypatch):
    import models.notificacao as modelo_notificacao

    documentos = [_doc(), _doc(tipo="justificacao_decidida")]
    monkeypatch.setattr(modelo_notificacao, "listar_por_utilizador", lambda uid, p, l: documentos)

    resposta = client.get("/me/notificacoes", headers=AUTH_HEADER)
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["quantidade"] == 2
    assert corpo["pagina"] == 1
    assert corpo["limite"] == 20
    assert corpo["tem_mais"] is False
    assert corpo["notificacoes"][0]["tipo"] == "comunicado"


def test_listar_pagina_invalida(client, conta):
    resposta = client.get("/me/notificacoes?pagina=abc", headers=AUTH_HEADER)
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_page"


def test_listar_parametro_nao_permitido(client, conta):
    resposta = client.get("/me/notificacoes?ordenar=asc", headers=AUTH_HEADER)
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_query"


def test_listar_tem_mais_quando_excede_limite(client, conta, monkeypatch):
    import models.notificacao as modelo_notificacao

    documentos = [_doc() for _ in range(21)]
    monkeypatch.setattr(modelo_notificacao, "listar_por_utilizador", lambda uid, p, l: documentos)

    resposta = client.get("/me/notificacoes", headers=AUTH_HEADER)
    corpo = resposta.get_json()
    assert corpo["quantidade"] == 20
    assert corpo["tem_mais"] is True


def test_marcar_lida_sucesso(client, conta, monkeypatch):
    import models.notificacao as modelo_notificacao

    documento = _doc(lida=True)
    monkeypatch.setattr(modelo_notificacao, "marcar_lida", lambda nid, uid: documento)

    resposta = client.patch(f"/me/notificacoes/{documento['_id']}/lida", headers=AUTH_HEADER)
    assert resposta.status_code == 200
    assert resposta.get_json()["lida"] is True


def test_marcar_lida_id_invalido(client, conta):
    resposta = client.patch("/me/notificacoes/id-invalido/lida", headers=AUTH_HEADER)
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_notification_id"


def test_marcar_lida_nao_encontrada(client, conta, monkeypatch):
    import models.notificacao as modelo_notificacao

    monkeypatch.setattr(modelo_notificacao, "marcar_lida", lambda nid, uid: None)

    resposta = client.patch(f"/me/notificacoes/{ObjectId()}/lida", headers=AUTH_HEADER)
    assert resposta.status_code == 404
