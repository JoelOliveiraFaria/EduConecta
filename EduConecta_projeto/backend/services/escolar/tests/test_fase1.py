"""Testes da Fase 1: eliminar aluno (RF10), editar aluno por Profissional
(RF09), e o conceito de diretor de turma (RF18/RF21/RF22)."""

from unittest.mock import MagicMock

from bson import ObjectId

AUTH_HEADER = {"Authorization": "Bearer qualquer-coisa"}


def utilizador(perfil="admin", **extra):
    base = {"id": str(ObjectId()), "nome": "Fulano", "perfil": perfil, "estado": "ativo"}
    base.update(extra)
    return base


# --- DELETE /alunos/<id> (RF10) ---------------------------------------------

def test_eliminar_aluno_admin_sucesso(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.aluno_controller as aluno_controller
    import models.aluno as modelo_aluno

    aluno_id = ObjectId()
    monkeypatch.setattr(
        modelo_aluno, "eliminar", lambda aid, por: {"_id": aluno_id, "nome": "Rui"}
    )
    eventos_publicados = []
    monkeypatch.setattr(
        aluno_controller, "publicar",
        lambda routing_key, payload: eventos_publicados.append((routing_key, payload)),
    )

    resposta = client.delete(f"/alunos/{aluno_id}", headers=AUTH_HEADER)
    assert resposta.status_code == 200
    assert resposta.get_json()["eliminado"] is True
    assert eventos_publicados == [("aluno.eliminado", {"aluno_id": str(aluno_id)})]


def test_eliminar_aluno_ja_eliminado(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import models.aluno as modelo_aluno

    monkeypatch.setattr(modelo_aluno, "eliminar", lambda aid, por: None)

    resposta = client.delete(f"/alunos/{ObjectId()}", headers=AUTH_HEADER)
    assert resposta.status_code == 404


def test_eliminar_aluno_nao_admin_bloqueado(client, autenticar):
    autenticar(utilizador(perfil="docente"))

    resposta = client.delete(f"/alunos/{ObjectId()}", headers=AUTH_HEADER)
    assert resposta.status_code == 403


# --- PATCH /alunos/<id> por Profissional (RF09) -----------------------------

def test_editar_aluno_profissional_da_turma(client, autenticar, monkeypatch):
    conta_id = str(ObjectId())
    turma_id = ObjectId()
    profissional_id = ObjectId()
    aluno_id = ObjectId()

    autenticar(utilizador(perfil="docente", id=conta_id))

    import controllers.aluno_controller as aluno_controller
    import models.aluno as modelo_aluno
    import models.turma as modelo_turma

    monkeypatch.setattr(
        aluno_controller,
        "obter_profissional_da_sessao",
        lambda: ({"_id": profissional_id, "perfil": "docente"}, None),
    )
    monkeypatch.setattr(
        modelo_aluno, "obter", lambda aid: {"_id": aluno_id, "turma_id": turma_id}
    )
    monkeypatch.setattr(modelo_turma, "esta_atribuido", lambda tid, pid: True)
    monkeypatch.setattr(
        modelo_aluno,
        "atualizar",
        lambda aid, alteracoes: {"_id": aluno_id, "nome": alteracoes.get("nome")},
    )

    resposta = client.patch(
        f"/alunos/{aluno_id}", headers=AUTH_HEADER, json={"nome": "Novo Nome"}
    )
    assert resposta.status_code == 200
    assert resposta.get_json()["nome"] == "Novo Nome"


def test_editar_aluno_profissional_fora_da_turma(client, autenticar, monkeypatch):
    turma_id = ObjectId()
    aluno_id = ObjectId()

    autenticar(utilizador(perfil="docente"))

    import controllers.aluno_controller as aluno_controller
    import models.aluno as modelo_aluno
    import models.turma as modelo_turma

    monkeypatch.setattr(
        aluno_controller,
        "obter_profissional_da_sessao",
        lambda: ({"_id": ObjectId(), "perfil": "docente"}, None),
    )
    monkeypatch.setattr(
        modelo_aluno, "obter", lambda aid: {"_id": aluno_id, "turma_id": turma_id}
    )
    monkeypatch.setattr(modelo_turma, "esta_atribuido", lambda tid, pid: False)

    resposta = client.patch(
        f"/alunos/{aluno_id}", headers=AUTH_HEADER, json={"nome": "Novo Nome"}
    )
    assert resposta.status_code == 403


def test_editar_aluno_sem_turma_bloqueia_profissional(client, autenticar, monkeypatch):
    aluno_id = ObjectId()

    autenticar(utilizador(perfil="educadora"))

    import controllers.aluno_controller as aluno_controller
    import models.aluno as modelo_aluno

    monkeypatch.setattr(
        aluno_controller,
        "obter_profissional_da_sessao",
        lambda: ({"_id": ObjectId(), "perfil": "educadora"}, None),
    )
    monkeypatch.setattr(modelo_aluno, "obter", lambda aid: {"_id": aluno_id, "turma_id": None})

    resposta = client.patch(
        f"/alunos/{aluno_id}", headers=AUTH_HEADER, json={"nome": "Novo Nome"}
    )
    assert resposta.status_code == 403


# --- GET /turmas/<id> (detalhe, sem conceito de diretor) --------------------

def test_obter_turma_admin(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import models.profissional as modelo_profissional
    import models.turma as modelo_turma

    turma_id = ObjectId()
    prof_id = ObjectId()

    monkeypatch.setattr(
        modelo_turma,
        "obter_detalhe",
        lambda tid: {
            "_id": turma_id,
            "nome": "5A",
            "ano_letivo": "2025/2026",
            "tipo": "basico",
            "profissionais_ids": [prof_id],
        },
    )
    monkeypatch.setattr(
        modelo_profissional,
        "listar_por_ids",
        lambda ids: [{"_id": prof_id, "nome": "Ana", "perfil": "docente"}],
    )

    resposta = client.get(f"/turmas/{turma_id}", headers=AUTH_HEADER)
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert "diretor_turma" not in corpo
    assert corpo["tipo"] == "basico"
    assert len(corpo["profissionais"]) == 1


def test_obter_turma_profissional_nao_atribuido(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="docente"))

    import controllers.turma_controller as turma_controller
    import models.turma as modelo_turma

    turma_id = ObjectId()
    monkeypatch.setattr(
        modelo_turma,
        "obter_detalhe",
        lambda tid: {"_id": turma_id, "nome": "5A", "ano_letivo": "2025/2026", "tipo": "basico", "profissionais_ids": []},
    )
    monkeypatch.setattr(
        turma_controller,
        "obter_profissional_da_sessao",
        lambda: ({"_id": ObjectId(), "perfil": "docente"}, None),
    )

    resposta = client.get(f"/turmas/{turma_id}", headers=AUTH_HEADER)
    assert resposta.status_code == 404


# --- PUT /turmas/<id>/profissionais/<id> — regra "1 docente por turma" -----

def test_associar_segundo_docente_e_rejeitado(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.turma_controller as turma_controller
    import models.profissional as modelo_profissional
    import models.turma as modelo_turma

    novo_prof_id = ObjectId()
    outro_prof_id = ObjectId()
    conta_id = ObjectId()

    monkeypatch.setattr(
        modelo_profissional,
        "obter",
        lambda pid: {"_id": novo_prof_id, "nome": "Novo Prof", "perfil": "docente", "utilizador_id": conta_id},
    )
    monkeypatch.setattr(
        turma_controller,
        "consultar_conta_profissional_auth",
        lambda conta_id, header: ({"id": str(conta_id), "nome": "Novo Prof", "perfil": "docente", "estado": "ativo"}, None),
    )
    monkeypatch.setattr(modelo_turma, "profissionais_atribuidos", lambda tid: [outro_prof_id])
    monkeypatch.setattr(
        modelo_profissional,
        "listar_por_ids",
        lambda ids: [{"_id": outro_prof_id, "perfil": "docente"}],
    )

    resposta = client.put(
        f"/turmas/{ObjectId()}/profissionais/{novo_prof_id}", headers=AUTH_HEADER
    )
    assert resposta.status_code == 409
    assert resposta.get_json()["error"] == "class_already_has_teacher"


def test_associar_educadora_sem_limite(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.turma_controller as turma_controller
    import models.profissional as modelo_profissional
    import models.turma as modelo_turma

    prof_id = ObjectId()
    conta_id = ObjectId()
    turma_id = ObjectId()

    monkeypatch.setattr(
        modelo_profissional,
        "obter",
        lambda pid: {"_id": prof_id, "nome": "Educadora", "perfil": "educadora", "utilizador_id": conta_id},
    )
    monkeypatch.setattr(
        turma_controller,
        "consultar_conta_profissional_auth",
        lambda conta_id, header: ({"id": str(conta_id), "nome": "Educadora", "perfil": "educadora", "estado": "ativo"}, None),
    )
    monkeypatch.setattr(
        modelo_turma,
        "adicionar_profissional",
        lambda tid, pid: {"_id": turma_id, "nome": "5A", "ano_letivo": "2025/2026", "tipo": "creche"},
    )

    resposta = client.put(
        f"/turmas/{turma_id}/profissionais/{prof_id}", headers=AUTH_HEADER
    )
    assert resposta.status_code == 200
