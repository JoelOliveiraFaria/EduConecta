import subprocess
import tempfile
from io import BytesIO

from bson import ObjectId
from flask import Blueprint, g, jsonify, request, send_file
from gridfs.errors import CorruptGridFile, NoFile
from pymongo.errors import PyMongoError

import models.anexo as modelo_anexo
import models.comunicado as modelo_comunicado
from db import MAX_FOTOGRAFIA_BYTES, MAX_VIDEO_BYTES
from utils.acesso import verificar_acesso
from utils.service_client import erro
from utils.video import analisar_mp4

"""Controller: listar, descarregar e carregar anexos (fotografias e vídeos)
de um comunicado. `_listar`/`_obter` são partilhadas pelos dois tipos — só
`carregar_video` não tem equivalente para fotografias, porque o upload de
fotografia fica em comunicado_controller.anexar_fotografia (feito antes de
este controller existir; mantido lá para não duplicar/mudar comportamento).
"""

bp = Blueprint("anexos", __name__)

BASE = "/turmas/<turma_id>/comunicados/<comunicado_id>"


def _autorizar(turma_id, comunicado_id, publicar=False):
    """Confirma acesso à turma (verificar_acesso) e que o comunicado existe e
    é acessível (ou editável, se publicar=True) por esta conta. Devolve
    (comunicado_id_canónico, None) no sucesso, ou (None, erro) na falha."""
    falha = verificar_acesso(turma_id, publicar=publicar)

    if falha is not None:
        return None, falha

    if not ObjectId.is_valid(comunicado_id):
        return None, erro("invalid_notice_id", "Identificador inválido.", 400)

    cid = str(ObjectId(comunicado_id))

    try:
        if publicar:
            doc = modelo_comunicado.obter_editavel(cid, g.turma_id, g.utilizador_id)
        else:
            doc = modelo_comunicado.obter_acessivel(cid, g.turma_id)
    except PyMongoError:
        return None, erro("database_unavailable", "Base de dados indisponível.", 503)

    if doc is None:
        return None, erro("notice_not_accessible", "Comunicado não acessível.", 404)

    return cid, None


def _listar(turma_id, comunicado_id, tipo):
    """Lista metadados dos anexos de um comunicado (sem o binário), com URLs
    prontas para GET direto. `tipo` é "fotografias" ou "videos"."""
    cid, falha = _autorizar(turma_id, comunicado_id)

    if falha is not None:
        return falha

    if (set(request.args) - {"antes_de"}
            or len(request.args.getlist("antes_de")) > 1):
        return erro("invalid_query", "Envia apenas um antes_de opcional.", 400)

    cursor = request.args.get("antes_de")

    if cursor is not None and not ObjectId.is_valid(cursor):
        return erro("invalid_cursor", "Cursor inválido.", 400)

    try:
        docs = modelo_anexo.listar_anexos(tipo, g.turma_id, cid, cursor, limite=20)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível listar os anexos.", 503)

    pagina = docs[:20]
    itens = []

    for doc in pagina:
        fid = str(doc["_id"])
        url = f"/turmas/{g.turma_id}/comunicados/{cid}/{tipo}/{fid}"
        meta = doc.get("metadata", {})
        item = {
            "id": fid,
            "tamanho_bytes": doc["length"],
            "tipo": "image/jpeg" if tipo == "fotografias" else "video/mp4",
            "url": url,
            "url_download": url + "?download=1",
        }

        for campo in ("largura", "altura", "duracao_segundos", "tem_audio"):
            if campo in meta:
                item[campo] = meta[campo]

        itens.append(item)

    return jsonify({
        "comunicado_id": cid,
        tipo: itens,
        "quantidade": len(itens),
        "limite": 20,
        "tem_mais": len(docs) > 20,
        "proximo_cursor": str(pagina[-1]["_id"]) if len(docs) > 20 else None,
    }), 200


def _obter(turma_id, comunicado_id, anexo_id, tipo):
    """Lê o binário de um anexo do GridFS e devolve-o como ficheiro (streaming
    via send_file), confirmando o tamanho lido contra o tamanho declarado
    (`ficheiro.length`) para não devolver um ficheiro truncado em silêncio."""
    cid, falha = _autorizar(turma_id, comunicado_id)

    if falha is not None:
        return falha

    if not ObjectId.is_valid(anexo_id):
        return erro("invalid_attachment_id", "Identificador inválido.", 400)

    if (set(request.args) - {"download"}
            or len(request.args.getlist("download")) > 1
            or request.args.get("download") not in {None, "1"}):
        return erro("invalid_query", "Apenas download=1 é permitido.", 400)

    limite = MAX_FOTOGRAFIA_BYTES if tipo == "fotografias" else MAX_VIDEO_BYTES

    try:
        ficheiro = modelo_anexo.obter_anexo(tipo, anexo_id, g.turma_id, cid)

        if ficheiro is None:
            return erro("attachment_not_accessible", "Anexo não acessível.", 404)

        with ficheiro:
            if not 0 < ficheiro.length <= limite:
                return erro("attachment_unavailable", "Tamanho inesperado.", 503)

            dados = ficheiro.read(limite + 1)

            if len(dados) != ficheiro.length:
                return erro("attachment_unavailable", "Anexo incompleto.", 503)

    except (NoFile, CorruptGridFile, PyMongoError):
        return erro("attachment_unavailable", "Não foi possível ler o anexo.", 503)

    extensao = "jpg" if tipo == "fotografias" else "mp4"
    resposta = send_file(
        BytesIO(dados),
        mimetype="image/jpeg" if tipo == "fotografias" else "video/mp4",
        download_name=f"educonecta-{ObjectId(anexo_id)}.{extensao}",
        as_attachment=request.args.get("download") == "1",
        conditional=True, etag=False, max_age=0,
    )
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


@bp.get(BASE + "/fotografias")
def listar_fotos(turma_id, comunicado_id):
    """Lista as fotografias anexadas a um comunicado."""
    return _listar(turma_id, comunicado_id, "fotografias")


@bp.get(BASE + "/fotografias/<fotografia_id>")
def obter_foto(turma_id, comunicado_id, fotografia_id):
    """Descarrega/mostra uma fotografia concreta."""
    return _obter(turma_id, comunicado_id, fotografia_id, "fotografias")


@bp.get(BASE + "/videos")
def listar_videos(turma_id, comunicado_id):
    """Lista os vídeos anexados a um comunicado."""
    return _listar(turma_id, comunicado_id, "videos")


@bp.get(BASE + "/videos/<video_id>")
def obter_video(turma_id, comunicado_id, video_id):
    """Descarrega/mostra um vídeo concreto."""
    return _obter(turma_id, comunicado_id, video_id, "videos")


@bp.post(BASE + "/videos")
def carregar_video(turma_id, comunicado_id):
    """Recebe, valida e guarda um vídeo anexado a um comunicado.

    Faz streaming do upload para um ficheiro temporário em blocos de 64KB,
    cortando assim que ultrapassa MAX_VIDEO_BYTES — evita carregar o vídeo
    inteiro em memória só para descobrir depois que é grande demais. Só
    depois de gravado em disco é que o ffprobe (utils/video.analisar_mp4)
    valida o conteúdo; o ficheiro temporário é sempre apagado no fim (bloco
    `with`), mesmo se a validação ou a gravação no GridFS falharem.
    """
    cid, falha = _autorizar(turma_id, comunicado_id, publicar=True)

    if falha is not None:
        return falha

    if request.mimetype != "multipart/form-data":
        return erro("unsupported_media_type", "Envia multipart/form-data.", 415)

    if (request.form or set(request.files) != {"video"}
            or len(request.files.getlist("video")) != 1):
        return erro("invalid_fields", "Envia apenas um ficheiro no campo video.", 400)

    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", mode="w+b") as tmp:
            tamanho = 0

            while True:
                bloco = request.files["video"].stream.read(64 * 1024)

                if not bloco:
                    break

                tamanho += len(bloco)

                if tamanho > MAX_VIDEO_BYTES:
                    return erro("file_too_large", "O vídeo deve ter até 25 MB.", 413)

                tmp.write(bloco)

            if tamanho == 0:
                return erro("empty_file", "O vídeo está vazio.", 400)

            tmp.flush()

            try:
                info = analisar_mp4(tmp.name)
            except subprocess.TimeoutExpired:
                return erro("video_analysis_timeout", "Análise excedeu dez segundos.", 400)
            except (subprocess.CalledProcessError, ValueError, TypeError,
                    KeyError, AttributeError, OverflowError):
                return erro(
                    "invalid_video",
                    "Envia MP4 H.264, com áudio AAC opcional, sem pistas adicionais.",
                    400,
                )

            tmp.seek(0)
            vid = ObjectId()
            nome = f"educonecta-{vid}.mp4"

            try:
                modelo_anexo.guardar_video(
                    tmp,
                    vid,
                    nome,
                    {
                        "comunicado_id": cid,
                        "turma_id": g.turma_id,
                        "criado_por": g.utilizador_id,
                        "tipo": "video/mp4",
                        **info,
                    },
                )
            except PyMongoError:
                return erro(
                    "database_unavailable",
                    "Carregamento não confirmado. Não repitas automaticamente.",
                    503,
                )

    except OSError:
        return erro(
            "video_processing_unavailable",
            "Ferramenta ou armazenamento temporário indisponível.",
            503,
        )

    return jsonify({
        "id": str(vid),
        "nome": nome,
        "tipo": "video/mp4",
        "comunicado_id": cid,
        "turma_id": g.turma_id,
        "tamanho_bytes": tamanho,
        **info,
    }), 201
