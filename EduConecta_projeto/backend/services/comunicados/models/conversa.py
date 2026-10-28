from datetime import datetime, timezone

from bson import ObjectId

from db import database


def serializar_conversa(documento):
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
    documento = {
        "_id": conversa_id,
        **contexto,
        "criado_em": datetime.now(timezone.utc),
    }
    database["conversas"].insert_one(documento)
    return documento


def obter_conversa_por_id(conversa_id):
    return database["conversas"].find_one({"_id": conversa_id})


def obter_conversa_participante(conversa_id, campo_participante, conta_id):
    return database["conversas"].find_one({
        "_id": conversa_id,
        campo_participante: conta_id,
    })


def listar_conversas_participante(filtro, limite):
    return list(
        database["conversas"]
        .find(filtro)
        .sort("_id", 1)
        .limit(limite + 1)
    )


def criar_mensagem(conversa_id, texto, enviado_por):
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
    return list(
        database["mensagens"]
        .find(filtro)
        .sort("_id", -1)
        .limit(limite + 1)
    )
