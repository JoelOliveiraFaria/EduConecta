"""Utilitário: publica eventos de domínio no RabbitMQ (Fase 2), para o
serviço `notificacoes` os consumir — exchange topic `educonecta.eventos`,
uma routing key por tipo de evento (ex: "comunicado.criado").

Publicação é "melhor esforço": se o RabbitMQ estiver em baixo ou a ligação
falhar, o evento é perdido (fica só um aviso nos logs) mas o pedido HTTP
principal nunca chega a falhar por causa disto — notificar é um efeito
secundário, nunca o motivo de recusar a publicação de um comunicado.
"""

import json
import logging
import os

import pika

logger = logging.getLogger(__name__)

EXCHANGE = "educonecta.eventos"


def publicar(routing_key, payload):
    """Publica `payload` (dict serializável em JSON) no exchange de eventos,
    com a routing key dada. Nunca levanta exceção — falhas ficam só no log."""
    try:
        parametros = pika.URLParameters(os.environ["RABBITMQ_URL"])
        parametros.socket_timeout = 3
        parametros.connection_attempts = 1
        with pika.BlockingConnection(parametros) as ligacao:
            canal = ligacao.channel()
            canal.exchange_declare(exchange=EXCHANGE, exchange_type="topic", durable=True)
            canal.basic_publish(
                exchange=EXCHANGE,
                routing_key=routing_key,
                body=json.dumps(payload).encode("utf-8"),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                ),
            )
    except (pika.exceptions.AMQPError, OSError, KeyError):
        logger.exception("Falha ao publicar evento '%s' no RabbitMQ.", routing_key)
