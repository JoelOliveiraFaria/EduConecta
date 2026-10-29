"""Model: acesso aos dados da coleção `notificacoes` — sem lógica de
negócio, só leitura/escrita. Quem decide o que gravar e para quem é
`utils/consumidor.py` (eventos RabbitMQ); quem lê é
`controllers/notificacao_controller.py` (GET /me/notificacoes).
"""

from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from db import notificacoes

TIPOS = {"comunicado", "justificacao_pendente", "justificacao_decidida"}


def criar(destinatario_utilizador_id, tipo, titulo, mensagem, referencia):
    """Grava uma notificação nova para um utilizador; devolve o documento inserido."""
    documento = {
        "destinatario_utilizador_id": destinatario_utilizador_id,
        "tipo": tipo,
        "titulo": titulo,
        "mensagem": mensagem,
        "referencia": referencia,
        "lida": False,
        "criada_em": datetime.now(timezone.utc),
    }
    resultado = notificacoes.insert_one(documento)
    documento["_id"] = resultado.inserted_id
    return documento


def listar_por_utilizador(utilizador_id, pagina, limite):
    """Notificações de um utilizador, mais recentes primeiro, paginadas (pede
    limite+1 para o controller saber se há próxima página sem fazer um count à parte)."""
    salto = (pagina - 1) * limite
    return list(
        notificacoes
        .find({"destinatario_utilizador_id": utilizador_id})
        .sort([("criada_em", -1), ("_id", -1)])
        .skip(salto)
        .limit(limite + 1)
    )


def marcar_lida(notificacao_id, utilizador_id):
    """Marca como lida, só se a notificação pertencer mesmo a este utilizador.

    Devolve o documento atualizado, ou None se não existir/não for deste utilizador.
    """
    return notificacoes.find_one_and_update(
        {"_id": ObjectId(notificacao_id), "destinatario_utilizador_id": utilizador_id},
        {"$set": {"lida": True}},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def serializar(doc):
    """Converte o documento interno na forma pública devolvida pela API."""
    return {
        "id": str(doc["_id"]),
        "tipo": doc["tipo"],
        "titulo": doc["titulo"],
        "mensagem": doc["mensagem"],
        "referencia": doc.get("referencia") or {},
        "lida": doc["lida"],
        "criada_em": doc["criada_em"].isoformat(timespec="milliseconds"),
    }
