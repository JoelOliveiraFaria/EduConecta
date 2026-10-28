from pymongo import ReturnDocument

from db import CAMPOS_TEXTO, database, registos


def contar_colecoes():
    return database.list_collection_names()


def serializar(documento):
    resultado = {
        "id": documento["_id"],
        "aluno_id": documento["aluno_id"],
        "turma_id": documento["turma_id"],
        "data": documento["data"],
        **{
            campo: documento.get(campo, "")
            for campo in CAMPOS_TEXTO
        },
        "criado_por": documento["criado_por"],
        "criado_em": documento["criado_em"].isoformat(
            timespec="milliseconds"
        ),
    }

    if documento.get("atualizado_em") is not None:
        resultado["atualizado_em"] = documento["atualizado_em"].isoformat(
            timespec="milliseconds"
        )

    return resultado


def inserir(documento):
    return registos.insert_one(documento)


def listar_por_aluno_turma(aluno_id, turma_id, limite=31):
    return (
        registos
        .find({"aluno_id": aluno_id, "turma_id": turma_id})
        .sort("data", -1)
        .limit(limite)
    )


def atualizar(aluno_id, turma_id, data_registo, criado_por, alteracoes):
    return registos.find_one_and_update(
        {
            "_id": f"{aluno_id}:{data_registo}",
            "aluno_id": aluno_id,
            "turma_id": turma_id,
            "criado_por": criado_por,
        },
        {"$set": alteracoes},
        return_document=ReturnDocument.AFTER,
    )
