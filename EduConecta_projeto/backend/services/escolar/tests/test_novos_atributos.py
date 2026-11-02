"""Testes: novos atributos opcionais acrescentados a aluno (data_nascimento,
morada), encarregado (morada, relacao), profissional (morada, data_admissao)
e turma (capacidade)."""

from bson import ObjectId

AUTH_HEADER = {"Authorization": "Bearer qualquer-coisa"}


def utilizador(perfil="admin", **extra):
    base = {"id": str(ObjectId()), "nome": "Fulano", "perfil": perfil, "estado": "ativo"}
    base.update(extra)
    return base


# --- aluno --------------------------------------------------------------

def test_criar_aluno_com_data_nascimento_e_morada(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import models.aluno as modelo_aluno

    novo_id = ObjectId()
    monkeypatch.setattr(
        modelo_aluno, "criar",
        lambda nome, numero_processo, data_nascimento=None, morada="": (
            novo_id,
            {
                "nome": nome, "numero_processo": numero_processo,
                "data_nascimento": data_nascimento, "morada": morada,
            },
        ),
    )

    resposta = client.post(
        "/alunos", headers=AUTH_HEADER,
        json={
            "nome": "Joao Silva", "numero_processo": "123",
            "data_nascimento": "2020-05-10", "morada": "Rua das Flores, 10",
        },
    )
    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["data_nascimento"] == "2020-05-10"
    assert corpo["morada"] == "Rua das Flores, 10"


def test_criar_aluno_data_nascimento_no_futuro_rejeitada(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/alunos", headers=AUTH_HEADER,
        json={"nome": "Joao Silva", "numero_processo": "123", "data_nascimento": "2999-01-01"},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_birth_date"


def test_criar_aluno_morada_demasiado_longa_rejeitada(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/alunos", headers=AUTH_HEADER,
        json={"nome": "Joao Silva", "numero_processo": "123", "morada": "a" * 201},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_address"


def test_atualizar_aluno_data_nascimento_e_morada(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import models.aluno as modelo_aluno

    aluno_id = ObjectId()
    monkeypatch.setattr(
        modelo_aluno, "atualizar",
        lambda aid, alteracoes: {"_id": aluno_id, **alteracoes},
    )

    resposta = client.patch(
        f"/alunos/{aluno_id}", headers=AUTH_HEADER,
        json={"data_nascimento": "2019-02-14", "morada": "Avenida Central, 5"},
    )
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["data_nascimento"] == "2019-02-14"
    assert corpo["morada"] == "Avenida Central, 5"


# --- encarregado ----------------------------------------------------------

def test_criar_encarregado_com_morada_e_relacao(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.encarregado_controller as encarregado_controller
    import models.encarregado as modelo_encarregado

    conta_id = str(ObjectId())
    monkeypatch.setattr(
        encarregado_controller, "criar_conta_utilizador",
        lambda nome, email, perfil, autorizacao: (
            {"id": conta_id, "email": email, "estado": "ativo", "deve_alterar_password": True},
            None,
        ),
    )
    monkeypatch.setattr(
        modelo_encarregado, "criar",
        lambda nome, cc, telemovel, utilizador_id, morada="", relacao=None: (
            ObjectId(),
            {
                "nome": nome, "cc": cc, "telemovel": telemovel, "utilizador_id": utilizador_id,
                "morada": morada, "relacao": relacao,
            },
        ),
    )

    resposta = client.post(
        "/encarregados", headers=AUTH_HEADER,
        json={
            "nome": "Ana Pais", "email": "ana@example.com", "cc": "12345678",
            "morada": "Rua Nova, 7", "relacao": "mae",
        },
    )
    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["morada"] == "Rua Nova, 7"
    assert corpo["relacao"] == "mae"


def test_criar_encarregado_relacao_invalida_rejeitada(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/encarregados", headers=AUTH_HEADER,
        json={
            "nome": "Ana Pais", "email": "ana@example.com", "cc": "12345678",
            "relacao": "avó",
        },
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_relation"


# --- profissional -----------------------------------------------------------

def test_criar_profissional_com_morada_e_data_admissao(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.profissional_controller as profissional_controller
    import models.profissional as modelo_profissional

    conta_id = str(ObjectId())
    monkeypatch.setattr(
        profissional_controller, "criar_conta_utilizador",
        lambda nome, email, perfil, autorizacao: (
            {"id": conta_id, "email": email, "estado": "ativo", "deve_alterar_password": True},
            None,
        ),
    )
    monkeypatch.setattr(
        modelo_profissional, "criar",
        lambda utilizador_id, nome, perfil, cc, telemovel, morada="", data_admissao=None: (
            ObjectId(),
            {
                "utilizador_id": utilizador_id, "nome": nome, "perfil": perfil, "cc": cc,
                "telemovel": telemovel, "morada": morada, "data_admissao": data_admissao,
            },
        ),
    )

    resposta = client.post(
        "/profissionais", headers=AUTH_HEADER,
        json={
            "nome": "Carlos Prof", "email": "carlos@example.com", "cc": "87654321",
            "perfil": "docente", "morada": "Praça Central, 1", "data_admissao": "2024-09-01",
        },
    )
    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["morada"] == "Praça Central, 1"
    assert corpo["data_admissao"] == "2024-09-01"


def test_criar_profissional_data_admissao_invalida_rejeitada(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/profissionais", headers=AUTH_HEADER,
        json={
            "nome": "Carlos Prof", "email": "carlos@example.com", "cc": "87654321",
            "perfil": "docente", "data_admissao": "01-09-2024",
        },
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_admission_date"


# --- turma ------------------------------------------------------------------

def test_criar_turma_com_capacidade(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import models.turma as modelo_turma

    novo_id = ObjectId()
    monkeypatch.setattr(
        modelo_turma, "criar",
        lambda nome, ano_letivo, tipo, capacidade=None: (
            novo_id,
            {"nome": nome, "ano_letivo": ano_letivo, "tipo": tipo, "capacidade": capacidade},
        ),
    )

    resposta = client.post(
        "/turmas", headers=AUTH_HEADER,
        json={"nome": "Sala Azul", "ano_letivo": "2025/2026", "tipo": "creche", "capacidade": 20},
    )
    assert resposta.status_code == 201
    assert resposta.get_json()["capacidade"] == 20


def test_criar_turma_capacidade_nao_inteira_rejeitada(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/turmas", headers=AUTH_HEADER,
        json={"nome": "Sala Azul", "ano_letivo": "2025/2026", "tipo": "creche", "capacidade": "vinte"},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_capacity"


def test_criar_turma_capacidade_fora_do_intervalo_rejeitada(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/turmas", headers=AUTH_HEADER,
        json={"nome": "Sala Azul", "ano_letivo": "2025/2026", "tipo": "creche", "capacidade": 0},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_capacity"


def test_criar_turma_capacidade_booleana_rejeitada(client, autenticar):
    """bool é subclasse de int em Python — tem de ser recusado explicitamente."""
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/turmas", headers=AUTH_HEADER,
        json={"nome": "Sala Azul", "ano_letivo": "2025/2026", "tipo": "creche", "capacidade": True},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_capacity"
