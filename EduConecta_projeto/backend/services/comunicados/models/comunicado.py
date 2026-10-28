from datetime import datetime, timezone

from bson import ObjectId

from db import database


def serializar(documento):
    return {
        "id": str(documento["_id"]),
        "turma_id": documento["turma_id"],
        "titulo": documento["titulo"],
        "texto": documento["texto"],
        "criado_em": documento["criado_em"].isoformat(
            timespec="milliseconds"
        ),
    }


def criar(turma_id, titulo, texto, criado_por):
    documento = {
        "_id": ObjectId(),
        "turma_id": turma_id,
        "titulo": titulo,
        "texto": texto,
        "criado_por": criado_por,
        "criado_em": datetime.now(timezone.utc),
    }
    database["comunicados"].insert_one(documento)
    return documento


def listar_por_turma(turma_id, pagina, limite):
    return list(
        database["comunicados"]
        .find({"turma_id": turma_id})
        .sort([("criado_em", -1), ("_id", -1)])
        .skip((pagina - 1) * limite)
        .limit(limite + 1)
    )


def obter_editavel(comunicado_id, turma_id, criado_por):
    return database["comunicados"].find_one(
        {
            "_id": ObjectId(comunicado_id),
            "turma_id": turma_id,
            "criado_por": criado_por,
        },
        {"_id": 1},
    )


def obter_acessivel(comunicado_id, turma_id):
    return database["comunicados"].find_one(
        {"_id": ObjectId(comunicado_id), "turma_id": turma_id},
        {"_id": 1},
    )
