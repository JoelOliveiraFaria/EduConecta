"""Testes: o diário só está disponível para turmas do tipo "creche" (RNF
de negócio pedido depois da Fase 1 — turmas "basico" não têm diário, só
assiduidade/faltas). Testa utils.acesso.verificar_acesso diretamente,
porque os testes de rotas mockam essa função inteira e nunca exercitam
esta verificação."""

import utils.acesso as acesso

CONTA_DOCENTE = {"id": "686f6f6f6f6f6f6f6f6f6f6a", "estado": "ativo", "perfil": "docente"}
TURMA_ID = "686f6f6f6f6f6f6f6f6f6f6f"
ALUNO_ID = "686f6f6f6f6f6f6f6f6f6f6e"


def _mock_consultar(monkeypatch, turma_tipo):
    def fake(url):
        if url.endswith("/me"):
            return CONTA_DOCENTE, None
        return (
            {
                "turma": {"id": TURMA_ID, "tipo": turma_tipo},
                "alunos": [{"id": ALUNO_ID}],
            },
            None,
        )

    monkeypatch.setattr(acesso, "consultar_servico", fake)


def test_turma_creche_e_aceite(app, monkeypatch):
    _mock_consultar(monkeypatch, "creche")
    with app.app_context():
        falha = acesso.verificar_acesso(TURMA_ID, ALUNO_ID)
    assert falha is None


def test_turma_basico_e_recusada(app, monkeypatch):
    _mock_consultar(monkeypatch, "basico")
    with app.app_context():
        falha = acesso.verificar_acesso(TURMA_ID, ALUNO_ID)
    assert falha is not None
    _resposta, estado = falha
    assert estado == 409


def test_turma_sem_tipo_e_recusada(app, monkeypatch):
    """Turmas criadas antes deste campo existir (sem `tipo`) também são
    recusadas — mais seguro do que assumir "creche" por omissão."""
    _mock_consultar(monkeypatch, None)
    with app.app_context():
        falha = acesso.verificar_acesso(TURMA_ID, ALUNO_ID)
    assert falha is not None
    _resposta, estado = falha
    assert estado == 409
