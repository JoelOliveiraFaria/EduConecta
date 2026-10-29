"""Consumidor RabbitMQ (Fase 2): liga-se ao exchange `educonecta.eventos`,
consome os eventos publicados pelos outros serviços e grava notificações
para quem deve ser avisado.

Corre numa thread de fundo, arrancada em app.py ao iniciar o processo
(uma por worker do gunicorn — todas ligam à mesma fila durável, o RabbitMQ
reparte as mensagens entre elas, nenhuma é processada duas vezes). Religa
automaticamente se a ligação cair (ex: o RabbitMQ ainda não estava pronto,
ou reiniciou).

Sem fila de mensagens mortas nem re-tentativas por mensagem: se o
processamento de uma mensagem falhar (exceção), fica só um aviso no log e
a mensagem é confirmada (ack) na mesma, para não bloquear a fila com uma
mensagem permanentemente "presa" — decisão de âmbito aceite para a Fase 2
(ver docs/fase-2-plano.md, secção "Fora de âmbito").
"""

import json
import logging
import os
import threading
import time

import pika

import models.auditoria as modelo_auditoria
import models.notificacao as modelo_notificacao
from utils.escolar_client import destinatarios_da_turma

logger = logging.getLogger(__name__)

EXCHANGE = "educonecta.eventos"
FILA = "notificacoes"
ROUTING_KEYS = (
    "aluno.eliminado",
    "comunicado.criado",
    "falta.justificacao.submetida",
    "falta.justificacao.decidida",
)


def tratar_aluno_eliminado(dados):
    """Não há ninguém específico a notificar — só fica o registo de auditoria
    como prova de que o evento foi recebido e processado."""
    modelo_auditoria.registar("aluno.eliminado", dados)


def tratar_comunicado_criado(dados):
    """Notifica os encarregados de educação dos alunos da turma do comunicado."""
    turma_id = dados.get("turma_id")
    titulo = dados.get("titulo", "")
    resolucao, falha = destinatarios_da_turma(turma_id)
    if falha is not None:
        logger.warning(
            "comunicado.criado: não foi possível resolver destinatários (%s).", falha
        )
        return
    for utilizador_id in resolucao.get("encarregados_utilizador_ids", []):
        modelo_notificacao.criar(
            utilizador_id,
            "comunicado",
            "Novo comunicado",
            f'Foi publicado um novo comunicado: "{titulo}".',
            {"turma_id": turma_id, "comunicado_id": dados.get("comunicado_id")},
        )


def tratar_justificacao_submetida(dados):
    """Notifica os profissionais (docente/educadora) atribuídos à turma de
    que há uma justificação de falta pendente de decisão."""
    turma_id = dados.get("turma_id")
    resolucao, falha = destinatarios_da_turma(turma_id)
    if falha is not None:
        logger.warning(
            "falta.justificacao.submetida: não foi possível resolver destinatários (%s).", falha
        )
        return
    for utilizador_id in resolucao.get("profissionais_utilizador_ids", []):
        modelo_notificacao.criar(
            utilizador_id,
            "justificacao_pendente",
            "Justificação de falta pendente",
            "Há uma justificação de falta à espera de decisão.",
            {"turma_id": turma_id, "aluno_id": dados.get("aluno_id"), "data": dados.get("data")},
        )


def tratar_justificacao_decidida(dados):
    """Notifica o encarregado que submeteu a justificação da decisão tomada.

    O destinatário já vem no próprio evento (quem submeteu a justificação
    originalmente) — não precisa de consultar o escolar.
    """
    utilizador_id = dados.get("destinatario_utilizador_id")
    if not utilizador_id:
        return
    estado = dados.get("estado")
    titulo = "Justificação aprovada" if estado == "aprovada" else "Justificação rejeitada"
    modelo_notificacao.criar(
        utilizador_id,
        "justificacao_decidida",
        titulo,
        f'A justificação da falta de {dados.get("data")} foi {estado}.',
        {"aluno_id": dados.get("aluno_id"), "data": dados.get("data"), "estado": estado},
    )


_TRATADORES = {
    "aluno.eliminado": tratar_aluno_eliminado,
    "comunicado.criado": tratar_comunicado_criado,
    "falta.justificacao.submetida": tratar_justificacao_submetida,
    "falta.justificacao.decidida": tratar_justificacao_decidida,
}


def processar_mensagem(canal, metodo, _propriedades, corpo):
    """Despacha uma mensagem recebida para o tratador da sua routing key.

    Apanha qualquer exceção de propósito (JSON inválido, tratador que falha
    a contactar outro serviço, bug inesperado): este é o limite externo do
    consumidor, uma mensagem malformada ou um erro não pode derrubar a
    ligação nem travar as mensagens seguintes da fila.
    """
    try:
        dados = json.loads(corpo.decode("utf-8"))
        tratador = _TRATADORES.get(metodo.routing_key)
        if tratador is not None:
            tratador(dados)
    except Exception:
        logger.exception(
            "Falha a processar evento '%s'; mensagem descartada.", metodo.routing_key
        )
    finally:
        canal.basic_ack(delivery_tag=metodo.delivery_tag)


def _ligar_e_consumir():
    parametros = pika.URLParameters(os.environ["RABBITMQ_URL"])
    with pika.BlockingConnection(parametros) as ligacao:
        canal = ligacao.channel()
        canal.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
        canal.queue_declare(queue=FILA, durable=True)
        for chave in ROUTING_KEYS:
            canal.queue_bind(exchange=EXCHANGE, queue=FILA, routing_key=chave)
        canal.basic_qos(prefetch_count=10)
        canal.basic_consume(queue=FILA, on_message_callback=processar_mensagem)
        canal.start_consuming()


def _ciclo_com_religacao():
    # Thread de fundo de longa duração: nunca pode morrer por uma exceção —
    # se a ligação cair, regista e tenta outra vez até o RabbitMQ voltar.
    while True:
        try:
            _ligar_e_consumir()
        except Exception:
            logger.exception("Consumidor RabbitMQ caiu; a tentar religar em 5s.")
            time.sleep(5)


def iniciar_em_fundo():
    """Arranca o consumidor numa thread daemon. Chamado uma vez a partir de
    app.py, exceto em testes (ver DISABLE_RABBITMQ_CONSUMER em conftest.py)."""
    thread = threading.Thread(target=_ciclo_com_religacao, daemon=True, name="rabbitmq-consumidor")
    thread.start()
    return thread
