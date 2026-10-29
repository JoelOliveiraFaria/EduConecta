"""Testes: criar profissional (docente/educadora/auxiliar) cria também a
conta de login, no mesmo espírito de POST /encarregados — já não recebe
um utilizador_id de uma conta existente; pede nome, email, cc, telemovel
(opcional) e perfil, e é o próprio auth que cria a conta e envia a
password temporária por email."""

from bson import ObjectId

AUTH_HEADER = {"Authorization": "Bearer qualquer-coisa"}


def utilizador(perfil="admin", **extra):
    base = {"id": str(ObjectId()), "nome": "Fulano", "perfil": perfil, "estado": "ativo"}
    base.update(extra)
    return base


def test_criar_profissional_sem_perfil_e_rejeitado(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/profissionais",
        headers=AUTH_HEADER,
        json={"nome": "Ana Prof", "email": "ana.prof@example.com", "cc": "12345678"},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_fields"


def test_criar_profissional_perfil_invalido(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/profissionais",
        headers=AUTH_HEADER,
        json={
            "nome": "Ana Prof",
            "email": "ana.prof@example.com",
            "cc": "12345678",
            "perfil": "admin",
        },
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_profile"


def test_criar_profissional_sem_cc_e_rejeitado(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/profissionais",
        headers=AUTH_HEADER,
        json={"nome": "Ana Prof", "email": "ana.prof@example.com", "perfil": "docente"},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_fields"


def test_criar_profissional_sucesso_cria_conta(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.profissional_controller as profissional_controller
    import models.profissional as modelo_profissional

    conta_id = str(ObjectId())
    chamada = {}

    def fake_criar_conta(nome, email, perfil, autorizacao):
        chamada["perfil"] = perfil
        return {
            "id": conta_id,
            "email": email,
            "estado": "ativo",
            "deve_alterar_password": True,
        }, None

    monkeypatch.setattr(profissional_controller, "criar_conta_utilizador", fake_criar_conta)

    profissional_id = ObjectId()
    monkeypatch.setattr(
        modelo_profissional,
        "criar",
        lambda utilizador_id, nome, perfil, cc, telemovel: (
            profissional_id,
            {
                "utilizador_id": utilizador_id,
                "nome": nome,
                "perfil": perfil,
                "cc": cc,
                "telemovel": telemovel,
            },
        ),
    )

    resposta = client.post(
        "/profissionais",
        headers=AUTH_HEADER,
        json={
            "nome": "Ana Prof",
            "email": "ana.prof@example.com",
            "cc": "12345678",
            "telemovel": "912345678",
            "perfil": "educadora",
        },
    )

    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["utilizador_id"] == conta_id
    assert corpo["perfil"] == "educadora"
    assert corpo["cc"] == "12345678"
    assert chamada["perfil"] == "educadora"


def test_criar_profissional_email_duplicado_propaga_409(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.profissional_controller as profissional_controller
    from flask import jsonify

    monkeypatch.setattr(
        profissional_controller,
        "criar_conta_utilizador",
        lambda nome, email, perfil, autorizacao: (
            None,
            (
                jsonify({"error": "email_already_registered", "message": "Já existe uma conta com esse email."}),
                409,
            ),
        ),
    )

    resposta = client.post(
        "/profissionais",
        headers=AUTH_HEADER,
        json={
            "nome": "Ana Prof",
            "email": "ja.existe@example.com",
            "cc": "12345678",
            "perfil": "docente",
        },
    )
    assert resposta.status_code == 409
    assert resposta.get_json()["error"] == "email_already_registered"


def test_criar_profissional_sem_admin_bloqueado(client, autenticar):
    autenticar(utilizador(perfil="docente"))

    resposta = client.post(
        "/profissionais",
        headers=AUTH_HEADER,
        json={
            "nome": "Ana Prof",
            "email": "ana.prof@example.com",
            "cc": "12345678",
            "perfil": "docente",
        },
    )
    assert resposta.status_code == 403
