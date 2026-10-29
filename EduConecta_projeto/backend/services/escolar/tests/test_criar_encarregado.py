"""Testes: criar encarregado de educação cria também a conta de login
(correção pedida depois de testar no Swagger — antes não pedia email nem
criava conta, por isso não dava para fazer login com esse encarregado).
Campos atuais: nome, email, cc (obrigatórios) e telemovel (opcional)."""

from bson import ObjectId

AUTH_HEADER = {"Authorization": "Bearer qualquer-coisa"}


def utilizador(perfil="admin", **extra):
    base = {"id": str(ObjectId()), "nome": "Fulano", "perfil": perfil, "estado": "ativo"}
    base.update(extra)
    return base


def test_criar_encarregado_sem_email_e_rejeitado(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/encarregados", headers=AUTH_HEADER, json={"nome": "Ana Pais", "cc": "12345678"}
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_fields"


def test_criar_encarregado_sem_cc_e_rejeitado(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/encarregados",
        headers=AUTH_HEADER,
        json={"nome": "Ana Pais", "email": "ana.pais@example.com"},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_fields"


def test_criar_encarregado_email_invalido(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/encarregados",
        headers=AUTH_HEADER,
        json={"nome": "Ana Pais", "email": "nao-e-email", "cc": "12345678"},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_email"


def test_criar_encarregado_cc_invalido(client, autenticar):
    autenticar(utilizador(perfil="admin"))

    resposta = client.post(
        "/encarregados",
        headers=AUTH_HEADER,
        json={"nome": "Ana Pais", "email": "ana.pais@example.com", "cc": "ab"},
    )
    assert resposta.status_code == 400
    assert resposta.get_json()["error"] == "invalid_cc"


def test_criar_encarregado_sucesso_cria_conta(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.encarregado_controller as encarregado_controller
    import models.encarregado as modelo_encarregado

    conta_id = str(ObjectId())
    chamada = {}

    def fake_criar_conta(nome, email, perfil, autorizacao):
        chamada["nome"] = nome
        chamada["email"] = email
        chamada["perfil"] = perfil
        return {
            "id": conta_id,
            "email": email,
            "estado": "ativo",
            "deve_alterar_password": True,
        }, None

    monkeypatch.setattr(encarregado_controller, "criar_conta_utilizador", fake_criar_conta)

    encarregado_id = ObjectId()
    monkeypatch.setattr(
        modelo_encarregado,
        "criar",
        lambda nome, cc, telemovel, utilizador_id: (
            encarregado_id,
            {"nome": nome, "cc": cc, "telemovel": telemovel, "utilizador_id": utilizador_id},
        ),
    )

    resposta = client.post(
        "/encarregados",
        headers=AUTH_HEADER,
        json={
            "nome": "Ana Pais",
            "email": "ana.pais@example.com",
            "cc": "12345678",
            "telemovel": "912345678",
        },
    )

    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["utilizador_id"] == conta_id
    assert corpo["email"] == "ana.pais@example.com"
    assert corpo["cc"] == "12345678"
    assert corpo["telemovel"] == "912345678"
    assert corpo["deve_alterar_password"] is True
    assert chamada["email"] == "ana.pais@example.com"
    assert chamada["perfil"] == "encarregado"


def test_criar_encarregado_sem_telemovel_opcional(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.encarregado_controller as encarregado_controller
    import models.encarregado as modelo_encarregado

    conta_id = str(ObjectId())

    monkeypatch.setattr(
        encarregado_controller,
        "criar_conta_utilizador",
        lambda nome, email, perfil, autorizacao: (
            {"id": conta_id, "email": email, "estado": "ativo", "deve_alterar_password": True},
            None,
        ),
    )
    monkeypatch.setattr(
        modelo_encarregado,
        "criar",
        lambda nome, cc, telemovel, utilizador_id: (
            ObjectId(),
            {"nome": nome, "cc": cc, "telemovel": telemovel, "utilizador_id": utilizador_id},
        ),
    )

    resposta = client.post(
        "/encarregados",
        headers=AUTH_HEADER,
        json={"nome": "Ana Pais", "email": "ana.pais@example.com", "cc": "12345678"},
    )
    assert resposta.status_code == 201
    assert resposta.get_json()["telemovel"] == ""


def test_criar_encarregado_email_duplicado_propaga_409(client, autenticar, monkeypatch):
    autenticar(utilizador(perfil="admin"))

    import controllers.encarregado_controller as encarregado_controller
    from flask import jsonify

    def fake_criar_conta(nome, email, perfil, autorizacao):
        return None, (
            jsonify({"error": "email_already_registered", "message": "Já existe uma conta com esse email."}),
            409,
        )

    monkeypatch.setattr(encarregado_controller, "criar_conta_utilizador", fake_criar_conta)

    resposta = client.post(
        "/encarregados",
        headers=AUTH_HEADER,
        json={"nome": "Ana Pais", "email": "ja.existe@example.com", "cc": "12345678"},
    )
    assert resposta.status_code == 409
    assert resposta.get_json()["error"] == "email_already_registered"


def test_criar_encarregado_sem_admin_bloqueado(client, autenticar):
    autenticar(utilizador(perfil="docente"))

    resposta = client.post(
        "/encarregados",
        headers=AUTH_HEADER,
        json={"nome": "Ana Pais", "email": "ana.pais@example.com", "cc": "12345678"},
    )
    assert resposta.status_code == 403
