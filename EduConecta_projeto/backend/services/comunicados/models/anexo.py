"""Model: acesso aos anexos (fotografias/vídeos) guardados em GridFS.

`tipo` é sempre "fotografias" ou "videos" — identifica qual dos dois buckets
definidos em db.py usar. Nenhuma validação de conteúdo acontece aqui (isso é
feito antes, em utils/imagem.py e utils/video.py); este módulo só grava e lê.
"""

from bson import ObjectId

from db import buckets, database


def guardar_fotografia(fotografia_id, conteudo, nome_download, metadata):
    """Grava os bytes já convertidos (JPEG) no bucket de fotografias."""
    buckets["fotografias"].put(
        conteudo,
        _id=fotografia_id,
        filename=nome_download,
        metadata=metadata,
    )


def guardar_video(ficheiro_temporario, video_id, nome, metadata):
    """Grava um vídeo (já validado por analisar_mp4) a partir de um ficheiro aberto."""
    buckets["videos"].put(
        ficheiro_temporario,
        _id=video_id,
        filename=nome,
        metadata=metadata,
    )


def listar_anexos(tipo, turma_id, comunicado_id, cursor=None, limite=20):
    """Lista metadados de anexos de um comunicado (sem o binário), paginados por _id decrescente.

    Consulta diretamente a coleção `<tipo>.files` que o GridFS cria — mais
    leve do que percorrer o bucket, já que só precisamos dos metadados.
    """
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
    """Abre um anexo para leitura, confirmando que pertence à turma/comunicado indicados."""
    return buckets[tipo].find_one({
        "_id": ObjectId(anexo_id),
        "metadata.turma_id": turma_id,
        "metadata.comunicado_id": comunicado_id,
    })
