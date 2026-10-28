from bson import ObjectId

from db import buckets, database


def guardar_fotografia(fotografia_id, conteudo, nome_download, metadata):
    buckets["fotografias"].put(
        conteudo,
        _id=fotografia_id,
        filename=nome_download,
        metadata=metadata,
    )


def guardar_video(ficheiro_temporario, video_id, nome, metadata):
    buckets["videos"].put(
        ficheiro_temporario,
        _id=video_id,
        filename=nome,
        metadata=metadata,
    )


def listar_anexos(tipo, turma_id, comunicado_id, cursor=None, limite=20):
    filtro = {"metadata.turma_id": turma_id, "metadata.comunicado_id": comunicado_id}

    if cursor is not None:
        filtro["_id"] = {"$lt": ObjectId(cursor)}

    return list(
        database[tipo + ".files"]
        .find(filtro, {"_id": 1, "length": 1, "metadata": 1})
        .sort("_id", -1)
        .limit(limite + 1)
    )


def obter_anexo(tipo, anexo_id, turma_id, comunicado_id):
    return buckets[tipo].find_one({
        "_id": ObjectId(anexo_id),
        "metadata.turma_id": turma_id,
        "metadata.comunicado_id": comunicado_id,
    })
