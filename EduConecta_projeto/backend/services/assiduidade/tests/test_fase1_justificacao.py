"""Testes da Fase 1: justificação de faltas (RF18, RF20, RF21, RF22)."""

from datetime import date
from io import BytesIO

AUTH_HEADER = {"Authorization": "Bearer qualquer-token"}
TURMA_ID = "6ae24e41252e5bf6b58984aa"
ALUNO_ID = "6ae24e41252e5bf6b58984ac"
DIA = "2026-01-05"


def _patch_consultar(monkeypatch, conta, por_url):
    """Faz com que toda a chamada `consultar(url)` (nos 3 módulos que a
    importam por nome: app, justificacao_controller, models.assiduidade)
    devolva (conta, None) para o /me do auth, ou o que `por_url` indicar
    para os outros URLs (escolar), por prefixo."""

    def fake(url):
        if url == "http://auth:8000/me":
            return conta, None
        for prefixo, resposta in por_url.items():
            if url.startswith(prefixo):
                return resposta
        raise AssertionError(f"URL não esperado em consultar(): {url}")

    monkeypatch.setattr("app.consultar", fake)
    monkeypatch.setattr("controllers.justificacao_controller.consultar", fake)
    monkeypatch.setattr("models.assiduidade.consultar", fake)


def _conta(perfil):
    return {"id": "6ae24e41252e5bf6b58984ab", "estado": "ativo", "perfil": perfil}


# --- POST .../justificacao (RF20) -------------------------------------------

def test_submeter_justificacao_sucesso_so_texto(client, monkeypatch):
    conta = _conta("encarregado")
    _patch_consultar(monkeypatch, conta, {
        "http://escolar:8000/me/alunos": ({"alunos": [{"id": ALUNO_ID}], "limite": 50}, None),
    })

    import models.assiduidade as modelo_assiduidade
    import models.justificacao as modelo_justificacao

    monkeypatch.setattr(
        modelo_assiduidade, "obter_registo",
        lambda aid, dia: {"estado": "falta", "turma_id": TURMA_ID},
    )
    monkeypatch.setattr(modelo_justificacao, "prazo_expirado", lambda dia_date: False)
    monkeypatch.setattr(
        modelo_justificacao, "submeter",
        lambda aid, tid, dia, motivo, aid_anexo, nome_anexo, conta_id: {
            "aluno_id": aid, "turma_id": tid, "data": dia, "motivo": motivo, "anexo_id": None,
            "estado": "pendente", "motivo_rejeicao": None,
            "submetida_em": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "decidida_em": None,
        },
    )
    import controllers.justificacao_controller as justificacao_controller

    eventos_publicados = []
    monkeypatch.setattr(
        justificacao_controller, "publicar",
        lambda routing_key, payload: eventos_publicados.append((routing_key, payload)),
    )

    resposta = client.post(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao",
        headers=AUTH_HEADER,
        data={"motivo": "Consulta médica"},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 201
    corpo = resposta.get_json()
    assert corpo["motivo"] == "Consulta médica"
    assert corpo["estado"] == "pendente"
    assert eventos_publicados == [(
        "falta.justificacao.submetida",
        {"aluno_id": ALUNO_ID, "turma_id": TURMA_ID, "data": DIA},
    )]


def test_submeter_justificacao_com_anexo(client, monkeypatch):
    conta = _conta("encarregado")
    _patch_consultar(monkeypatch, conta, {
        "http://escolar:8000/me/alunos": ({"alunos": [{"id": ALUNO_ID}], "limite": 50}, None),
    })

    import models.assiduidade as modelo_assiduidade
    import models.justificacao as modelo_justificacao

    monkeypatch.setattr(
        modelo_assiduidade, "obter_registo",
        lambda aid, dia: {"estado": "falta", "turma_id": TURMA_ID},
    )
    monkeypatch.setattr(modelo_justificacao, "prazo_expirado", lambda dia_date: False)
    monkeypatch.setattr(modelo_justificacao, "guardar_anexo", lambda dados, nome, tipo: "anexo-id-123")
    monkeypatch.setattr(
        modelo_justificacao, "submeter",
        lambda aid, tid, dia, motivo, aid_anexo, nome_anexo, conta_id: {
            "aluno_id": aid, "turma_id": tid, "data": dia, "motivo": motivo, "anexo_id": aid_anexo,
            "estado": "pendente", "motivo_rejeicao": None,
            "submetida_em": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "decidida_em": None,
        },
    )
    import controllers.justificacao_controller as justificacao_controller

    monkeypatch.setattr(justificacao_controller, "publicar", lambda routing_key, payload: None)

    resposta = client.post(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao",
        headers=AUTH_HEADER,
        data={"anexo": (BytesIO(b"conteudo-do-atestado"), "atestado.pdf")},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 201
    assert resposta.get_json()["tem_anexo"] is True


def test_submeter_justificacao_sem_motivo_nem_anexo(client, monkeypatch):
    conta = _conta("encarregado")
    _patch_consultar(monkeypatch, conta, {
        "http://escolar:8000/me/alunos": ({"alunos": [{"id": ALUNO_ID}], "limite": 50}, None),
    })

    resposta = client.post(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao",
        headers=AUTH_HEADER,
        data={},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 400


def test_submeter_justificacao_sem_falta_registada(client, monkeypatch):
    conta = _conta("encarregado")
    _patch_consultar(monkeypatch, conta, {
        "http://escolar:8000/me/alunos": ({"alunos": [{"id": ALUNO_ID}], "limite": 50}, None),
    })

    import models.assiduidade as modelo_assiduidade

    monkeypatch.setattr(modelo_assiduidade, "obter_registo", lambda aid, dia: None)

    resposta = client.post(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao",
        headers=AUTH_HEADER,
        data={"motivo": "Doente"},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 404
    assert resposta.get_json()["error"] == "absence_not_found"


def test_submeter_justificacao_prazo_expirado(client, monkeypatch):
    conta = _conta("encarregado")
    _patch_consultar(monkeypatch, conta, {
        "http://escolar:8000/me/alunos": ({"alunos": [{"id": ALUNO_ID}], "limite": 50}, None),
    })

    import models.assiduidade as modelo_assiduidade
    import models.justificacao as modelo_justificacao

    monkeypatch.setattr(
        modelo_assiduidade, "obter_registo",
        lambda aid, dia: {"estado": "falta", "turma_id": TURMA_ID},
    )
    monkeypatch.setattr(modelo_justificacao, "prazo_expirado", lambda dia_date: True)

    resposta = client.post(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao",
        headers=AUTH_HEADER,
        data={"motivo": "Doente"},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 409
    assert resposta.get_json()["error"] == "deadline_expired"


def test_submeter_justificacao_educando_nao_acessivel(client, monkeypatch):
    conta = _conta("encarregado")
    _patch_consultar(monkeypatch, conta, {
        "http://escolar:8000/me/alunos": ({"alunos": [], "limite": 50}, None),
    })

    resposta = client.post(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao",
        headers=AUTH_HEADER,
        data={"motivo": "Doente"},
        content_type="multipart/form-data",
    )
    assert resposta.status_code == 404
    assert resposta.get_json()["error"] == "student_not_accessible"


# --- PUT .../aprovar e .../rejeitar (RF18/RF21/RF22) ------------------------
# Já não existe "diretor de turma": qualquer docente/educadora atribuído à
# turma pode decidir — a verificação reaproveita alunos_autorizados, por
# isso o mock é da mesma rota que consultar_turma/marcar já usam.

def test_aprovar_justificacao_profissional_atribuido(client, monkeypatch):
    conta_id = "6ae24e41252e5bf6b58984ab"
    conta = _conta("docente")
    conta["id"] = conta_id
    _patch_consultar(monkeypatch, conta, {
        f"http://escolar:8000/me/turmas/{TURMA_ID}/alunos": (
            {"turma": {"id": TURMA_ID}, "alunos": [], "quantidade": 0, "limite": 50}, None
        ),
    })

    import models.justificacao as modelo_justificacao

    monkeypatch.setattr(
        modelo_justificacao, "obter",
        lambda aid, dia: {"turma_id": TURMA_ID, "estado": "pendente"},
    )
    monkeypatch.setattr(
        modelo_justificacao, "decidir",
        lambda aid, dia, estado, motivo, conta_id: {
            "aluno_id": aid, "data": dia, "motivo": "x", "anexo_id": None,
            "estado": "aprovada", "motivo_rejeicao": None,
            "submetida_por": "6ae24e41252e5bf6b58984ad",
            "submetida_em": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "decidida_em": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        },
    )
    import controllers.justificacao_controller as justificacao_controller

    eventos_publicados = []
    monkeypatch.setattr(
        justificacao_controller, "publicar",
        lambda routing_key, payload: eventos_publicados.append((routing_key, payload)),
    )

    resposta = client.put(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao/aprovar", headers=AUTH_HEADER
    )
    assert resposta.status_code == 200
    assert resposta.get_json()["estado"] == "aprovada"
    assert eventos_publicados == [(
        "falta.justificacao.decidida",
        {
            "aluno_id": ALUNO_ID, "data": DIA, "estado": "aprovada",
            "destinatario_utilizador_id": "6ae24e41252e5bf6b58984ad",
        },
    )]


def test_aprovar_justificacao_profissional_nao_atribuido(client, monkeypatch):
    conta = _conta("docente")
    falha_escolar = (
        None,
        ({"error": "resource_not_accessible", "message": "Recurso não acessível."}, 404),
    )

    _patch_consultar(monkeypatch, conta, {
        f"http://escolar:8000/me/turmas/{TURMA_ID}/alunos": falha_escolar,
    })

    import models.justificacao as modelo_justificacao

    monkeypatch.setattr(
        modelo_justificacao, "obter",
        lambda aid, dia: {"turma_id": TURMA_ID, "estado": "pendente"},
    )

    resposta = client.put(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao/aprovar", headers=AUTH_HEADER
    )
    assert resposta.status_code == 404


def test_rejeitar_justificacao_exige_motivo(client, monkeypatch):
    conta = _conta("docente")
    _patch_consultar(monkeypatch, conta, {})

    resposta = client.put(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao/rejeitar",
        headers=AUTH_HEADER,
        json={},
    )
    assert resposta.status_code == 400


def test_rejeitar_justificacao_sucesso(client, monkeypatch):
    conta_id = "6ae24e41252e5bf6b58984ab"
    conta = _conta("educadora")
    conta["id"] = conta_id
    _patch_consultar(monkeypatch, conta, {
        f"http://escolar:8000/me/turmas/{TURMA_ID}/alunos": (
            {"turma": {"id": TURMA_ID}, "alunos": [], "quantidade": 0, "limite": 50}, None
        ),
    })

    import models.justificacao as modelo_justificacao

    monkeypatch.setattr(
        modelo_justificacao, "obter",
        lambda aid, dia: {"turma_id": TURMA_ID, "estado": "pendente"},
    )
    monkeypatch.setattr(
        modelo_justificacao, "decidir",
        lambda aid, dia, estado, motivo, conta_id: {
            "aluno_id": aid, "data": dia, "motivo": "x", "anexo_id": None,
            "estado": "rejeitada", "motivo_rejeicao": motivo,
            "submetida_por": "6ae24e41252e5bf6b58984ad",
            "submetida_em": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            "decidida_em": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        },
    )
    import controllers.justificacao_controller as justificacao_controller

    monkeypatch.setattr(justificacao_controller, "publicar", lambda routing_key, payload: None)

    resposta = client.put(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao/rejeitar",
        headers=AUTH_HEADER,
        json={"motivo_rejeicao": "Falta a mais de 3 dias úteis da data da falta."},
    )
    assert resposta.status_code == 200
    corpo = resposta.get_json()
    assert corpo["estado"] == "rejeitada"
    assert corpo["motivo_rejeicao"]


def test_decidir_justificacao_inexistente(client, monkeypatch):
    conta = _conta("docente")
    _patch_consultar(monkeypatch, conta, {})

    import models.justificacao as modelo_justificacao

    monkeypatch.setattr(modelo_justificacao, "obter", lambda aid, dia: None)

    resposta = client.put(
        f"/alunos/{ALUNO_ID}/faltas/{DIA}/justificacao/aprovar", headers=AUTH_HEADER
    )
    assert resposta.status_code == 404


# --- modelo: prazo_expirado --------------------------------------------------

def test_prazo_expirado_calcula_dias_uteis():
    import models.justificacao as modelo_justificacao

    falta_segunda = date(2026, 1, 5)  # segunda-feira
    # +3 dias uteis = quinta 2026-01-08; sexta ainda dentro do prazo (8),
    # sabado/domingo nao contam, segunda seguinte (12) ja esta fora.
    assert modelo_justificacao.prazo_expirado(falta_segunda, hoje=date(2026, 1, 8)) is False
    assert modelo_justificacao.prazo_expirado(falta_segunda, hoje=date(2026, 1, 12)) is True
