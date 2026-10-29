"""Testes: tratadores de eventos do consumidor RabbitMQ (Fase 2).

Não testam a ligação real ao RabbitMQ (isso exigiria um broker a correr) —
só a lógica de processamento de cada tipo de evento, isolada por
monkeypatch, mais o despacho/ack em `processar_mensagem`.
"""

import json

import utils.consumidor as consumidor


def test_tratar_aluno_eliminado_grava_auditoria(monkeypatch):
    import models.auditoria as modelo_auditoria

    chamadas = []
    monkeypatch.setattr(modelo_auditoria, "registar", lambda tipo, dados: chamadas.append((tipo, dados)))

    consumidor.tratar_aluno_eliminado({"aluno_id": "abc123"})

    assert chamadas == [("aluno.eliminado", {"aluno_id": "abc123"})]


def test_tratar_comunicado_criado_notifica_encarregados(monkeypatch):
    import models.notificacao as modelo_notificacao

    monkeypatch.setattr(
        consumidor,
        "destinatarios_da_turma",
        lambda turma_id: ({"encarregados_utilizador_ids": ["u1", "u2"], "profissionais_utilizador_ids": []}, None),
    )
    criados = []
    monkeypatch.setattr(
        modelo_notificacao, "criar",
        lambda destinatario, tipo, titulo, mensagem, referencia: criados.append(destinatario),
    )

    consumidor.tratar_comunicado_criado({"turma_id": "t1", "comunicado_id": "c1", "titulo": "Reunião"})

    assert criados == ["u1", "u2"]


def test_tratar_comunicado_criado_sem_destinatarios_nao_falha(monkeypatch):
    monkeypatch.setattr(consumidor, "destinatarios_da_turma", lambda turma_id: (None, "dependency_unavailable"))

    consumidor.tratar_comunicado_criado({"turma_id": "t1", "comunicado_id": "c1", "titulo": "Reunião"})


def test_tratar_justificacao_submetida_notifica_profissionais(monkeypatch):
    import models.notificacao as modelo_notificacao

    monkeypatch.setattr(
        consumidor,
        "destinatarios_da_turma",
        lambda turma_id: ({"profissionais_utilizador_ids": ["p1"], "encarregados_utilizador_ids": []}, None),
    )
    criados = []
    monkeypatch.setattr(
        modelo_notificacao, "criar",
        lambda destinatario, tipo, titulo, mensagem, referencia: criados.append((destinatario, tipo)),
    )

    consumidor.tratar_justificacao_submetida({"turma_id": "t1", "aluno_id": "a1", "data": "2026-03-05"})

    assert criados == [("p1", "justificacao_pendente")]


def test_tratar_justificacao_decidida_notifica_encarregado(monkeypatch):
    import models.notificacao as modelo_notificacao

    criados = []
    monkeypatch.setattr(
        modelo_notificacao, "criar",
        lambda destinatario, tipo, titulo, mensagem, referencia: criados.append((destinatario, tipo, titulo)),
    )

    consumidor.tratar_justificacao_decidida({
        "destinatario_utilizador_id": "enc1",
        "aluno_id": "a1",
        "data": "2026-03-05",
        "estado": "aprovada",
    })

    assert criados == [("enc1", "justificacao_decidida", "Justificação aprovada")]


def test_tratar_justificacao_decidida_sem_destinatario_nao_falha(monkeypatch):
    import models.notificacao as modelo_notificacao

    chamado = []
    monkeypatch.setattr(modelo_notificacao, "criar", lambda *a, **k: chamado.append(True))

    consumidor.tratar_justificacao_decidida({"aluno_id": "a1", "data": "2026-03-05", "estado": "rejeitada"})

    assert chamado == []


class _MetodoFalso:
    def __init__(self, routing_key, delivery_tag=1):
        self.routing_key = routing_key
        self.delivery_tag = delivery_tag


class _CanalFalso:
    def __init__(self):
        self.acks = []

    def basic_ack(self, delivery_tag):
        self.acks.append(delivery_tag)


def test_processar_mensagem_despacha_e_faz_ack(monkeypatch):
    chamadas = []
    monkeypatch.setitem(consumidor._TRATADORES, "aluno.eliminado", lambda dados: chamadas.append(dados))

    canal = _CanalFalso()
    corpo = json.dumps({"aluno_id": "abc"}).encode("utf-8")

    consumidor.processar_mensagem(canal, _MetodoFalso("aluno.eliminado"), None, corpo)

    assert chamadas == [{"aluno_id": "abc"}]
    assert canal.acks == [1]


def test_processar_mensagem_rotina_desconhecida_so_faz_ack(monkeypatch):
    canal = _CanalFalso()
    corpo = json.dumps({}).encode("utf-8")

    consumidor.processar_mensagem(canal, _MetodoFalso("evento.desconhecido"), None, corpo)

    assert canal.acks == [1]


def test_processar_mensagem_json_invalido_faz_ack_mesmo_assim(monkeypatch):
    canal = _CanalFalso()

    consumidor.processar_mensagem(canal, _MetodoFalso("aluno.eliminado"), None, b"nao e json")

    assert canal.acks == [1]


def test_processar_mensagem_tratador_que_falha_faz_ack_mesmo_assim(monkeypatch):
    def _rebenta(dados):
        raise RuntimeError("falha a propósito")

    monkeypatch.setitem(consumidor._TRATADORES, "aluno.eliminado", _rebenta)

    canal = _CanalFalso()
    corpo = json.dumps({}).encode("utf-8")

    consumidor.processar_mensagem(canal, _MetodoFalso("aluno.eliminado"), None, corpo)

    assert canal.acks == [1]
