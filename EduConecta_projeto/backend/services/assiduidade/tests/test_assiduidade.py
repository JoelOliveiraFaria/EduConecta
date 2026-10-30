AUTH_HEADER = {"Authorization": "Bearer qualquer-token"}
TURMA_ID = "6ae24e41252e5bf6b58984aa"
ALUNO_ID = "6ae24e41252e5bf6b58984ac"


def test_health(client):
    resposta = client.get("/health")
    assert resposta.status_code == 200
    assert resposta.get_json()["status"] == "ok"


def test_ready_ok(client, monkeypatch):
    class FakeDB:
        def list_collection_names(self):
            return []

    monkeypatch.setattr("controllers.health_controller.database", FakeDB())
    resposta = client.get("/ready")
    assert resposta.status_code == 200


def test_ready_falha(client, monkeypatch):
    from pymongo.errors import PyMongoError

    class FakeDB:
        def list_collection_names(self):
            raise PyMongoError()

    monkeypatch.setattr("controllers.health_controller.database", FakeDB())
    resposta = client.get("/ready")
    assert resposta.status_code == 503


def test_sem_token_bloqueado(client):
    resposta = client.get(f"/alunos/{ALUNO_ID}/assiduidade?inicio=2026-01-01&fim=2026-01-01")
    assert resposta.status_code == 401


def test_consultar_falha_propaga(client, monkeypatch):
    monkeypatch.setattr("app.consultar", lambda url: (None, ({"error": "x"}, 503)))
    resposta = client.get(
        f"/alunos/{ALUNO_ID}/assiduidade?inicio=2026-01-01&fim=2026-01-01",
        headers=AUTH_HEADER,
    )
    assert resposta.status_code == 503


def test_perfil_sem_permissao(client, conta_encarregado):
    resposta = client.get(f"/turmas/{TURMA_ID}/assiduidade?data=2026-01-01", headers=AUTH_HEADER)
    assert resposta.status_code == 403


def test_consultar_turma_data_invalida(client, conta_docente):
    resposta = client.get(f"/turmas/{TURMA_ID}/assiduidade?data=not-a-date", headers=AUTH_HEADER)
    assert resposta.status_code == 400


def test_consultar_turma_sucesso(client, conta_docente, monkeypatch):
    resposta_escolar = {
        "alunos": [{"id": ALUNO_ID, "nome": "Ana", "turma_id": TURMA_ID}],
        "turma": {"id": TURMA_ID},
        "quantidade": 1,
        "limite": 50,
    }
    monkeypatch.setattr("models.assiduidade.consultar", lambda url: (resposta_escolar, None))
    monkeypatch.setattr("models.assiduidade.procurar_marcacoes_turma", lambda dia, ids: {})

    resposta = client.get(f"/turmas/{TURMA_ID}/assiduidade?data=2026-01-01", headers=AUTH_HEADER)

    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["quantidade"] == 1
    assert corpo["alunos"][0]["estado"] == "por_marcar"
    assert corpo["contagem"]["por_marcar"] == 1


def test_marcar_campos_invalidos(client, conta_docente):
    resposta = client.put(
        f"/turmas/{TURMA_ID}/alunos/{ALUNO_ID}/assiduidade/2026-01-01",
        json={"estado": "inexistente", "versao": 0},
        headers=AUTH_HEADER,
    )
    assert resposta.status_code == 400


def test_marcar_sucesso(client, conta_docente, monkeypatch):
    resposta_escolar = {
        "alunos": [{"id": ALUNO_ID, "nome": "Ana", "turma_id": TURMA_ID}],
        "turma": {"id": TURMA_ID},
        "quantidade": 1,
        "limite": 50,
    }
    monkeypatch.setattr("models.assiduidade.consultar", lambda url: (resposta_escolar, None))

    import datetime

    doc = {
        "estado": "presente",
        "versao": 1,
        "atualizado_em": datetime.datetime.now(datetime.timezone.utc),
        "turma_id": TURMA_ID,
        "atualizado_por": "quem-marcou",
    }
    monkeypatch.setattr(
        "models.assiduidade.marcar_estado",
        lambda aid, tid, dia, estado, versao, conta_id: doc,
    )

    resposta = client.put(
        f"/turmas/{TURMA_ID}/alunos/{ALUNO_ID}/assiduidade/2026-01-01",
        json={"estado": "presente", "versao": 0},
        headers=AUTH_HEADER,
    )

    assert resposta.status_code == 200
    assert resposta.get_json()["estado"] == "presente"


def test_consultar_educando_intervalo_invalido(client, conta_encarregado):
    resposta = client.get(
        f"/alunos/{ALUNO_ID}/assiduidade?inicio=2026-02-01&fim=2026-01-01",
        headers=AUTH_HEADER,
    )
    assert resposta.status_code == 400


def test_consultar_educando_sucesso(client, conta_encarregado, monkeypatch):
    resposta_escolar = {"alunos": [{"id": ALUNO_ID}], "limite": 50}
    monkeypatch.setattr("app.consultar", lambda url: (
        {"id": conta_encarregado["id"], "estado": "ativo", "perfil": "encarregado"}, None
    ))
    monkeypatch.setattr(
        "controllers.assiduidade_controller.consultar", lambda url: (resposta_escolar, None)
    )
    monkeypatch.setattr("models.assiduidade.procurar_marcacoes_aluno", lambda aid, inicio, fim: {})

    resposta = client.get(
        f"/alunos/{ALUNO_ID}/assiduidade?inicio=2026-01-01&fim=2026-01-02",
        headers=AUTH_HEADER,
    )

    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["quantidade"] == 2


def _marcar_com_estado(client, monkeypatch, estado, publicados):
    import datetime

    resposta_escolar = {
        "alunos": [{"id": ALUNO_ID, "nome": "Ana", "turma_id": TURMA_ID}],
        "turma": {"id": TURMA_ID},
        "quantidade": 1,
        "limite": 50,
    }
    monkeypatch.setattr("models.assiduidade.consultar", lambda url: (resposta_escolar, None))
    doc = {
        "estado": estado,
        "versao": 1,
        "atualizado_em": datetime.datetime.now(datetime.timezone.utc),
        "turma_id": TURMA_ID,
        "atualizado_por": "quem-marcou",
    }
    monkeypatch.setattr("models.assiduidade.marcar_estado", lambda *a: doc)
    monkeypatch.setattr(
        "controllers.assiduidade_controller.publicar",
        lambda chave, payload: publicados.append((chave, payload)),
    )
    return client.put(
        f"/turmas/{TURMA_ID}/alunos/{ALUNO_ID}/assiduidade/2026-01-01",
        json={"estado": estado, "versao": 0},
        headers=AUTH_HEADER,
    )


def test_marcar_falta_publica_evento(client, conta_docente, monkeypatch):
    publicados = []
    resposta = _marcar_com_estado(client, monkeypatch, "falta", publicados)

    assert resposta.status_code == 200
    assert publicados == [
        ("falta.registada", {"aluno_id": ALUNO_ID, "turma_id": TURMA_ID, "data": "2026-01-01"})
    ]


def test_marcar_presente_nao_publica_evento(client, conta_docente, monkeypatch):
    publicados = []
    resposta = _marcar_com_estado(client, monkeypatch, "presente", publicados)

    assert resposta.status_code == 200
    assert publicados == []
