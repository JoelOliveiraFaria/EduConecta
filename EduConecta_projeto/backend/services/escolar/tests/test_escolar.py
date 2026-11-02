from unittest.mock import MagicMock

from bson import ObjectId

AUTH_HEADER = {"Authorization": "Bearer qualquer-coisa"}


def utilizador(perfil="admin", **extra):
    base = {"id": str(ObjectId()), "nome": "Fulano", "perfil": perfil, "estado": "ativo"}
    base.update(extra)
    return base


def test_health(client):
    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.get_json()["status"] == "ok"


def test_ready_falha_bd(client, monkeypatch):
    import controllers.health_controller as health_controller
    from pymongo.errors import PyMongoError

    monkeypatch.setattr(
        health_controller.database,
        "list_collection_names",
        MagicMock(side_effect=PyMongoError()),
    )
    resposta = client.get("/ready")
    assert resposta.status_code == 503


def test_rota_protegida_sem_token(client):
    resposta = client.get("/alunos")
    assert resposta.status_code == 401
    assert resposta.get_json()["error"] == "authentication_required"


def test_rota_protegida_token_mal_formado(client):
    resposta = client.get("/alunos", headers={"Authorization": "Token abc"})
    assert resposta.status_code == 401


def test_admin_acede_a_rota_generica(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import models.aluno as modelo_aluno

    monkeypatch.setattr(modelo_aluno, "listar", lambda: [])

    resposta = client.get("/alunos", headers=AUTH_HEADER)
    assert resposta.status_code == 200
    assert resposta.get_json()["alunos"] == []


def test_perfil_sem_permissao_e_bloqueado(client, autenticar):
    # "docente" nao esta na lista de perfis pessoais de /me/alunos nem e admin
    autenticar(utilizador(perfil="docente"))

    resposta = client.get("/me/alunos", headers=AUTH_HEADER)
    assert resposta.status_code == 403
    assert resposta.get_json()["error"] == "forbidden"


def test_encarregado_acede_a_me_alunos(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="encarregado"))

    import models.aluno as modelo_aluno
    import models.encarregado as modelo_encarregado

    encarregado_id = ObjectId()
    monkeypatch.setattr(
        modelo_encarregado,
        "obter_por_utilizador",
        lambda utilizador_id: {"_id": encarregado_id, "nome": "Mae"},
    )
    monkeypatch.setattr(modelo_aluno, "listar_por_encarregado", lambda eid: [])

    resposta = client.get("/me/alunos", headers=AUTH_HEADER)
    assert resposta.status_code == 200
    assert resposta.get_json()["encarregado"]["nome"] == "Mae"


def test_criar_aluno_validacao(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post("/alunos", headers=AUTH_HEADER, json={"nome": "A"})
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_name"


def test_criar_aluno_sucesso(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import models.aluno as modelo_aluno

    novo_id = ObjectId()
    monkeypatch.setattr(
        modelo_aluno,
        "criar",
        lambda nome, numero_processo, data_nascimento=None, morada="": (
            novo_id,
            {
                "nome": nome, "numero_processo": numero_processo,
                "data_nascimento": data_nascimento, "morada": morada,
            },
        ),
    )

    resposta = client.post(
        "/alunos",
        headers=AUTH_HEADER,
        json={"nome": "Joao Silva", "numero_processo": "123"},
    )
    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["id"] == str(novo_id)
    assert corpo["nome"] == "Joao Silva"


def test_validar_chat_participante_invalido(client, autenticar):
    conta_id = str(ObjectId())
    autenticar(utilizador(perfil="docente", id=conta_id))

    resposta = client.post(
        "/me/chat/validar",
        headers=AUTH_HEADER,
        json={
            "aluno_id": str(ObjectId()),
            "profissional_utilizador_id": str(ObjectId()),
            "encarregado_utilizador_id": str(ObjectId()),
        },
    )
    # conta_atual != profissional_utilizador_id -> participante invalido
    assert resposta.status_code == 403


def test_validar_chat_sucesso(client, autenticar, monkeypatch):
    conta_id = str(ObjectId())
    encarregado_conta_id = str(ObjectId())
    aluno_id = ObjectId()
    turma_id = ObjectId()
    profissional_id = ObjectId()
    encarregado_id = ObjectId()

    autenticar(utilizador(perfil="docente", id=conta_id))

    import models.aluno as modelo_aluno
    import models.encarregado as modelo_encarregado
    import models.profissional as modelo_profissional
    import models.turma as modelo_turma

    monkeypatch.setattr(
        modelo_profissional,
        "obter_para_chat",
        lambda uid: {"_id": profissional_id, "perfil": "docente"},
    )
    monkeypatch.setattr(
        modelo_encarregado, "obter_para_chat", lambda uid: {"_id": encarregado_id}
    )
    monkeypatch.setattr(
        modelo_aluno, "obter_para_chat", lambda aid, eid: {"turma_id": turma_id}
    )
    monkeypatch.setattr(
        modelo_turma, "obter_para_chat", lambda tid, pid: {"_id": turma_id}
    )

    resposta = client.post(
        "/me/chat/validar",
        headers=AUTH_HEADER,
        json={
            "aluno_id": str(aluno_id),
            "profissional_utilizador_id": conta_id,
            "encarregado_utilizador_id": encarregado_conta_id,
        },
    )

    assert resposta.status_code == 200
    assert resposta.get_json()["autorizado"] is True
