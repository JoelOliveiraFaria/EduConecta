"""Model: acesso aos anexos (fotografias/vídeos) guardados em GridFS.

`tipo` é sempre "fotografias" ou "videos" — identifica qual dos dois buckets
definidos em db.py usar. Nenhuma validação de conteúdo acontece aqui (isso é
feito antes, em utils/imagem.py e utils/video.py); este módulo só grava e lê.

Os dois buckets são partilhados por dois "donos" diferentes, distinguidos
pelo campo de metadata presente: `metadata.comunicado_id` (anexos de um
comunicado) ou `metadata.conversa_id` (anexos de uma mensagem de chat) —
nunca os dois ao mesmo tempo no mesmo ficheiro.
"""

from bson import ObjectId
from gridfs.errors import NoFile

from db import buckets, database


def guardar_fotografia(fotografia_id, conteudo, nome_download, metadata):
    """Grava os bytes já convertidos (JPEG) no bucket de fotografias, associados a um comunicado."""
    buckets["fotografias"].put(
        conteudo,
        _id=fotografia_id,
        filename=nome_download,
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
    """Abre um anexo de comunicado para leitura, confirmando que pertence à turma/comunicado indicados."""
    return buckets[tipo].find_one({
        "_id": ObjectId(anexo_id),
        "metadata.turma_id": turma_id,
        "metadata.comunicado_id": comunicado_id,
    })


def eliminar_anexos_comunicado(turma_id, comunicado_id):
    """Apaga do GridFS todos os anexos (fotografias e vídeos) de um comunicado,
    antes/depois de o próprio comunicado ser eliminado — evita ficar lixo
    órfão nos buckets. Ignora ficheiros que já não existam (NoFile), já que
    o objetivo é só garantir que não sobra nada, não é grave se já faltar."""
    for tipo in ("fotografias", "videos"):
        ficheiros = database[tipo + ".files"].find(
            {"metadata.turma_id": turma_id, "metadata.comunicado_id": comunicado_id},
            {"_id": 1},
        )
        for ficheiro in ficheiros:
            try:
                buckets[tipo].delete(ficheiro["_id"])
            except NoFile:
                pass


# --- Anexos de mensagens de chat (fotografia/vídeo numa conversa) ----------

def guardar_fotografia_mensagem(fotografia_id, conteudo, nome_download, metadata):
    """Grava uma fotografia anexada a uma mensagem de chat (metadata.conversa_id)."""
    buckets["fotografias"].put(
        conteudo,
        _id=fotografia_id,
        filename=nome_download,
        metadata=metadata,
    )


def guardar_video_mensagem(ficheiro_temporario, video_id, nome, metadata):
    """Grava um vídeo (já validado por analisar_mp4) anexado a uma mensagem de chat."""
    buckets["videos"].put(
        ficheiro_temporario,
        _id=video_id,
        filename=nome,
        metadata=metadata,
    )


def obter_anexo_mensagem(tipo, anexo_id, conversa_id):
    """Abre um anexo de mensagem de chat para leitura, confirmando que
    pertence mesmo a esta conversa."""
    return buckets[tipo].find_one({
        "_id": ObjectId(anexo_id),
        "metadata.conversa_id": conversa_id,
    })
