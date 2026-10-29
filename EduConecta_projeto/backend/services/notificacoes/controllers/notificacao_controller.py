"""Controller: notificações do próprio utilizador autenticado (Fase 2).

Não há rota para listar as notificações de outra pessoa — só "as minhas".
A criação de notificações não tem endpoint HTTP próprio: só acontece a
partir do consumidor RabbitMQ (ver utils/consumidor.py), nunca por pedido
direto de um cliente.
"""

from bson import ObjectId
from flask import Blueprint, g, jsonify, request
from pymongo.errors import PyMongoError

import models.notificacao as modelo_notificacao
from utils.http_client import erro

bp = Blueprint("notificacoes", __name__)


@bp.get("/me/notificacoes")
def listar_minhas_notificacoes():
    """Lista as notificações do utilizador autenticado, mais recentes primeiro, paginado."""
    if set(request.args) - {"pagina"}:
        return erro("invalid_query", "O único parâmetro permitido é pagina.", 400)

    valores_pagina = request.args.getlist("pagina")
    if len(valores_pagina) > 1:
        return erro("invalid_page", "Envia apenas um valor para pagina.", 400)

    try:
        pagina = int(request.args.get("pagina", "1"))
        if not 1 <= pagina <= 1000:
            raise ValueError
    except ValueError:
        return erro("invalid_page", "A página deve ser um inteiro entre 1 e 1000.", 400)

    limite = 20

    try:
        documentos = modelo_notificacao.listar_por_utilizador(g.conta_id, pagina, limite)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar as notificações.", 503)

    tem_mais = len(documentos) > limite
    notificacoes = [modelo_notificacao.serializar(doc) for doc in documentos[:limite]]

    return jsonify({
        "notificacoes": notificacoes,
        "quantidade": len(notificacoes),
        "pagina": pagina,
        "limite": limite,
        "tem_mais": tem_mais,
    }), 200


@bp.patch("/me/notificacoes/<notificacao_id>/lida")
def marcar_notificacao_lida(notificacao_id):
    """Marca uma notificação do próprio utilizador autenticado como lida."""
    if not ObjectId.is_valid(notificacao_id):
        return erro("invalid_notification_id", "O identificador da notificação é inválido.", 400)

    try:
        documento = modelo_notificacao.marcar_lida(notificacao_id, g.conta_id)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível atualizar a notificação.", 503)

    if documento is None:
        return erro("notification_not_found", "Notificação não encontrada.", 404)

    return jsonify(modelo_notificacao.serializar(documento)), 200
