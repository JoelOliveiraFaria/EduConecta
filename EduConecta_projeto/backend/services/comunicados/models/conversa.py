"""Model: acesso às coleções `conversas` e `mensagens` do chat.

O `_id` de uma conversa não é gerado pelo Mongo — é um hash determinístico
dos três participantes (ver chat_controller.criar_conversa), por isso a
mesma combinação aluno/profissional/encarregado produz sempre a mesma
conversa, sem precisar de a procurar antes de criar.
"""

from datetime import datetime, timezone

from bson import ObjectId

from db import database


def serializar_conversa(documento):
    """Converte o documento da conversa no formato JSON devolvido pela API."""
    return {
        "id": documento["_id"],
        "aluno_id": documento["aluno_id"],
        "profissional_utilizador_id": documento[
            "profissional_utilizador_id"
        ],
        "encarregado_utilizador_id": documento[
            "encarregado_utilizador_id"
        ],
        "criado_em": documento["criado_em"].isoformat(
            timespec="milliseconds"
        ),
    }


def serializar_mensagem(documento, conta_id):
    """Converte uma mensagem em JSON, marcando `enviada_por_mim` relativo a conta_id."""
    return {
        "id": str(documento["_id"]),
        "conversa_id": documento["conversa_id"],
        "texto": documento["texto"],
        "enviada_por_mim": documento["enviado_por"] == conta_id,
        "criado_em": documento["criado_em"].isoformat(
            timespec="milliseconds"
        ),
    }


def criar_conversa(conversa_id, contexto):
    """Cria a conversa com o _id determinístico; levanta DuplicateKeyError se já existir
    (o controller trata isso como "conversa já existe, devolve a existente")."""
    documento = {
        "_id": conversa_id,
        **contexto,
        "criado_em": datetime.now(timezone.utc),
    }
    database["conversas"].insert_one(documento)
    return documento


def obter_conversa_por_id(conversa_id):
    """Devolve a conversa pelo _id (hash), sem verificar participante."""
    return database["conversas"].find_one({"_id": conversa_id})


def obter_conversa_participante(conversa_id, campo_participante, conta_id):
    """Devolve a conversa só se conta_id for mesmo um dos participantes
    (campo_participante é 'profissional_utilizador_id' ou 'encarregado_utilizador_id',
    consoante o perfil de quem pede)."""
    return database["conversas"].find_one({
        "_id": conversa_id,
        campo_participante: conta_id,
    })


def listar_conversas_participante(filtro, limite):
    """Conversas onde a conta é participante, paginadas por _id ascendente."""
    return list(
        database["conversas"]
        .find(filtro)
        .sort("_id", 1)
        .limit(limite + 1)
    )


def criar_mensagem(conversa_id, texto, enviado_por):
    """Regista uma mensagem numa conversa já validada pelo controller."""
    documento = {
        "_id": ObjectId(),
        "conversa_id": conversa_id,
        "texto": texto,
        "enviado_por": enviado_por,
        "criado_em": datetime.now(timezone.utc),
    }
    database["mensagens"].insert_one(documento)
    return documento


def listar_mensagens(filtro, limite):
    """Mensagens que batem com o filtro (conversa + cursor opcional), mais recentes primeiro."""
    return list(
        database["mensagens"]
        .find(filtro)
        .sort("_id", -1)
        .limit(limite + 1)
    )
