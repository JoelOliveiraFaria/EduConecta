"""Testes: GET /internal/turmas/<id>/destinatarios (Fase 2) — endpoint
chamado só pelo consumidor do serviço notificacoes, autenticado por uma
chave partilhada (X-Internal-Key), não por sessão de utilizador."""

from bson import ObjectId

CHAVE_INTERNA_HEADER = {"X-Internal-Key": "chave-de-teste"}


def test_sem_chave_interna_bloqueado(client):
    resposta = client.get(f"/internal/turmas/{ObjectId()}/destinatarios")
    assert resposta.status_code == 403
    assert resposta.get_json()["error"] == "forbidden"


def test_chave_interna_errada_bloqueado(client):
    resposta = client.get(
        f"/internal/turmas/{ObjectId()}/destinatarios",
        headers={"X-Internal-Key": "chave-errada"},
    )
    assert resposta.status_code == 403


def test_turma_id_invalido(client):
    resposta = client.get("/internal/turmas/id-invalido/destinatarios", headers=CHAVE_INTERNA_HEADER)
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_class_id"


def test_turma_nao_encontrada(client, monkeypatch):
    import models.turma as modelo_turma

    monkeypatch.setattr(modelo_turma, "profissionais_atribuidos", lambda tid: None)

    resposta = client.get(f"/internal/turmas/{ObjectId()}/destinatarios", headers=CHAVE_INTERNA_HEADER)
    assert resposta.status_code == 404
    assert resposta.get_json()["error"] == "class_not_found"


def test_resolve_profissionais_e_encarregados(client, monkeypatch):
    import models.aluno as modelo_aluno
    import models.encarregado as modelo_encarregado
    import models.profissional as modelo_profissional
    import models.turma as modelo_turma

    turma_id = ObjectId()
    prof_id = ObjectId()
    enc_id = ObjectId()
    prof_conta_id = ObjectId()
    enc_conta_id = ObjectId()

    monkeypatch.setattr(modelo_turma, "profissionais_atribuidos", lambda tid: [prof_id])
    monkeypatch.setattr(
        modelo_profissional, "listar_por_ids",
        lambda ids: [{"_id": prof_id, "utilizador_id": prof_conta_id}],
    )
    monkeypatch.setattr(modelo_aluno, "listar_encarregados_ids_por_turma", lambda tid: [enc_id])
    monkeypatch.setattr(
        modelo_encarregado, "listar_por_ids",
        lambda ids: [{"_id": enc_id, "utilizador_id": enc_conta_id}],
    )

    resposta = client.get(f"/internal/turmas/{turma_id}/destinatarios", headers=CHAVE_INTERNA_HEADER)
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["profissionais_utilizador_ids"] == [str(prof_conta_id)]
    assert corpo["encarregados_utilizador_ids"] == [str(enc_conta_id)]


def test_sem_profissionais_nem_encarregados(client, monkeypatch):
    import models.aluno as modelo_aluno
    import models.encarregado as modelo_encarregado
    import models.profissional as modelo_profissional
    import models.turma as modelo_turma

    monkeypatch.setattr(modelo_turma, "profissionais_atribuidos", lambda tid: [])
    monkeypatch.setattr(modelo_profissional, "listar_por_ids", lambda ids: [])
    monkeypatch.setattr(modelo_aluno, "listar_encarregados_ids_por_turma", lambda tid: [])
    monkeypatch.setattr(modelo_encarregado, "listar_por_ids", lambda ids: [])

    resposta = client.get(f"/internal/turmas/{ObjectId()}/destinatarios", headers=CHAVE_INTERNA_HEADER)
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["profissionais_utilizador_ids"] == []
    assert corpo["encarregados_utilizador_ids"] == []
