from io import BytesIO

from bson import ObjectId
from flask import Blueprint, g, jsonify, request, send_file
from gridfs.errors import CorruptGridFile, NoFile
from pymongo.errors import PyMongoError

import models.anexo as modelo_anexo
import models.comunicado as modelo_comunicado
from db import MAX_FOTOGRAFIA_BYTES
from utils.acesso import verificar_acesso
from utils.service_client import erro

"""Controller: listar e descarregar fotografias de um comunicado (o upload
em si fica em comunicado_controller.anexar_fotografia, feito antes de este
controller existir; mantido lá para não duplicar/mudar comportamento).

Vídeo deixou de ser um anexo de comunicado — passou a ser um tipo de
mensagem de chat (ver chat_controller.py), por isso as rotas de vídeo que
existiam aqui foram removidas.
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


@bp.get(BASE + "/fotografias")
def listar_fotos(turma_id, comunicado_id):
    """Lista as fotografias anexadas a um comunicado, com URLs prontas para GET direto."""
    tipo = "fotografias"
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
            "tipo": "image/jpeg",
            "url": url,
            "url_download": url + "?download=1",
        }

        for campo in ("largura", "altura"):
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


@bp.get(BASE + "/fotografias/<fotografia_id>")
def obter_foto(turma_id, comunicado_id, fotografia_id):
    """Lê o binário de uma fotografia do GridFS e devolve-o como ficheiro
    (streaming via send_file), confirmando o tamanho lido contra o tamanho
    declarado (`ficheiro.length`) para não devolver um ficheiro truncado
    em silêncio."""
    cid, falha = _autorizar(turma_id, comunicado_id)

    if falha is not None:
        return falha

    if not ObjectId.is_valid(fotografia_id):
        return erro("invalid_attachment_id", "Identificador inválido.", 400)

    if (set(request.args) - {"download"}
            or len(request.args.getlist("download")) > 1
            or request.args.get("download") not in {None, "1"}):
        return erro("invalid_query", "Apenas download=1 é permitido.", 400)

    try:
        ficheiro = modelo_anexo.obter_anexo("fotografias", fotografia_id, g.turma_id, cid)

        if ficheiro is None:
            return erro("attachment_not_accessible", "Anexo não acessível.", 404)

        with ficheiro:
            if not 0 < ficheiro.length <= MAX_FOTOGRAFIA_BYTES:
                return erro("attachment_unavailable", "Tamanho inesperado.", 503)

            dados = ficheiro.read(MAX_FOTOGRAFIA_BYTES + 1)

            if len(dados) != ficheiro.length:
                return erro("attachment_unavailable", "Anexo incompleto.", 503)

    except (NoFile, CorruptGridFile, PyMongoError):
        return erro("attachment_unavailable", "Não foi possível ler o anexo.", 503)

    resposta = send_file(
        BytesIO(dados),
        mimetype="image/jpeg",
        download_name=f"educonecta-{ObjectId(fotografia_id)}.jpg",
        as_attachment=request.args.get("download") == "1",
        conditional=True, etag=False, max_age=0,
    )
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


