from bson import ObjectId
from flask import Blueprint, g, jsonify, request
from PIL import Image, UnidentifiedImageError
from pymongo.errors import PyMongoError

import models.anexo as modelo_anexo
import models.comunicado as modelo_comunicado
from db import MAX_FOTOGRAFIA_BYTES
from utils.acesso import verificar_acesso
from utils.eventos import publicar
from utils.imagem import preparar_fotografia
from utils.service_client import erro

"""Controller: publicar, editar, eliminar e listar comunicados de uma turma,
e anexar fotografias a um comunicado (listar/descarregar fotografias fica em
anexo_controller.py; vídeo deixou de ser um anexo de comunicado — passou
para mensagens de chat, ver chat_controller.py)."""

bp = Blueprint("comunicados", __name__)


@bp.post("/turmas/<turma_id>/comunicados")
def publicar_comunicado(turma_id):
    """Cria um comunicado na turma — só docente/educadora atribuídos a ela."""
    falha = verificar_acesso(turma_id, publicar=True)

    if falha is not None:
        return falha

    if not request.is_json:
        return erro(
            "unsupported_media_type",
            "Envia Content-Type: application/json.",
            415,
        )

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict) or set(dados) != {"titulo", "texto"}:
        return erro(
            "invalid_fields",
            "Envia apenas os campos obrigatórios titulo e texto.",
            400,
        )

    titulo = dados["titulo"]
    texto = dados["texto"]

    if (
        not isinstance(titulo, str)
        or not 1 <= len(titulo.strip()) <= 150
    ):
        return erro(
            "invalid_title",
            "O título deve ter entre 1 e 150 caracteres.",
            400,
        )

    if (
        not isinstance(texto, str)
        or not 1 <= len(texto.strip()) <= 5000
    ):
        return erro(
            "invalid_text",
            "O texto deve ter entre 1 e 5000 caracteres.",
            400,
        )

    try:
        documento = modelo_comunicado.criar(
            g.turma_id, titulo.strip(), texto.strip(), g.utilizador_id
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível guardar o comunicado.",
            503,
        )

    publicar("comunicado.criado", {
        "comunicado_id": str(documento["_id"]),
        "turma_id": g.turma_id,
        "titulo": documento["titulo"],
    })

    return jsonify(modelo_comunicado.serializar(documento)), 201


@bp.get("/turmas/<turma_id>/comunicados")
def listar_comunicados(turma_id):
    """Lista comunicados de uma turma, paginados — qualquer perfil com acesso à turma."""
    falha = verificar_acesso(turma_id)

    if falha is not None:
        return falha

    if set(request.args) - {"pagina"}:
        return erro(
            "invalid_query",
            "O único parâmetro permitido é pagina.",
            400,
        )

    valores_pagina = request.args.getlist("pagina")

    if len(valores_pagina) > 1:
        return erro(
            "invalid_page",
            "Envia apenas um valor para pagina.",
            400,
        )

    try:
        pagina = int(request.args.get("pagina", "1"))

        if not 1 <= pagina <= 1000:
            raise ValueError

    except ValueError:
        return erro(
            "invalid_page",
            "A página deve ser um inteiro entre 1 e 1000.",
            400,
        )

    limite = 20

    try:
        documentos = modelo_comunicado.listar_por_turma(g.turma_id, pagina, limite)

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar os comunicados.",
            503,
        )

    tem_mais = len(documentos) > limite

    comunicados = [
        modelo_comunicado.serializar(documento)
        for documento in documentos[:limite]
    ]

    return jsonify({
        "turma_id": g.turma_id,
        "comunicados": comunicados,
        "quantidade": len(comunicados),
        "pagina": pagina,
        "limite": limite,
        "tem_mais": tem_mais,
    }), 200


@bp.patch("/turmas/<turma_id>/comunicados/<comunicado_id>")
def atualizar_comunicado(turma_id, comunicado_id):
    """Atualização parcial de titulo e/ou texto — só o autor do comunicado."""
    falha = verificar_acesso(turma_id, publicar=True)

    if falha is not None:
        return falha

    if not ObjectId.is_valid(comunicado_id):
        return erro(
            "invalid_notice_id",
            "O identificador do comunicado é inválido.",
            400,
        )

    comunicado_canonico = str(ObjectId(comunicado_id))

    if not request.is_json:
        return erro(
            "unsupported_media_type",
            "Envia o pedido com Content-Type: application/json.",
            415,
        )

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return erro(
            "invalid_json",
            "O corpo do pedido deve ser um objeto JSON válido.",
            400,
        )

    campos_permitidos = {"titulo", "texto"}

    if not dados or set(dados) - campos_permitidos:
        return erro(
            "invalid_fields",
            "Envia pelo menos um dos campos titulo e/ou texto.",
            400,
        )

    alteracoes = {}

    if "titulo" in dados:
        titulo = dados["titulo"]

        if not isinstance(titulo, str) or not 1 <= len(titulo.strip()) <= 150:
            return erro(
                "invalid_title",
                "O título deve ter entre 1 e 150 caracteres.",
                400,
            )

        alteracoes["titulo"] = titulo.strip()

    if "texto" in dados:
        texto = dados["texto"]

        if not isinstance(texto, str) or not 1 <= len(texto.strip()) <= 5000:
            return erro(
                "invalid_text",
                "O texto deve ter entre 1 e 5000 caracteres.",
                400,
            )

        alteracoes["texto"] = texto.strip()

    try:
        documento = modelo_comunicado.atualizar(
            comunicado_canonico, g.turma_id, g.utilizador_id, alteracoes
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível atualizar o comunicado.",
            503,
        )

    if documento is None:
        return erro(
            "notice_not_editable",
            "O comunicado não existe ou não é editável por esta conta.",
            404,
        )

    return jsonify(modelo_comunicado.serializar(documento)), 200


@bp.delete("/turmas/<turma_id>/comunicados/<comunicado_id>")
def eliminar_comunicado(turma_id, comunicado_id):
    """Elimina um comunicado e todos os seus anexos (GridFS) — só o autor."""
    falha = verificar_acesso(turma_id, publicar=True)

    if falha is not None:
        return falha

    if not ObjectId.is_valid(comunicado_id):
        return erro(
            "invalid_notice_id",
            "O identificador do comunicado é inválido.",
            400,
        )

    comunicado_canonico = str(ObjectId(comunicado_id))

    try:
        eliminado = modelo_comunicado.eliminar(
            comunicado_canonico, g.turma_id, g.utilizador_id
        )

        if eliminado:
            modelo_anexo.eliminar_anexos_comunicado(g.turma_id, comunicado_canonico)

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível eliminar o comunicado.",
            503,
        )

    if not eliminado:
        return erro(
            "notice_not_editable",
            "O comunicado não existe ou não é editável por esta conta.",
            404,
        )

    return jsonify({"id": comunicado_canonico, "eliminado": True}), 200


@bp.post(
    "/turmas/<turma_id>/comunicados/"
    "<comunicado_id>/fotografias"
)
def anexar_fotografia(turma_id, comunicado_id):
    """Processa e anexa uma fotografia a um comunicado já existente, criado por
    esta própria conta (ver models.comunicado.obter_editavel). A conversão da
    imagem (formato, tamanho, EXIF) está em utils/imagem.py."""
    falha = verificar_acesso(turma_id, publicar=True)

    if falha is not None:
        return falha

    if not ObjectId.is_valid(comunicado_id):
        return erro(
            "invalid_notice_id",
            "O identificador do comunicado é inválido.",
            400,
        )

    comunicado_canonico = str(ObjectId(comunicado_id))

    try:
        comunicado = modelo_comunicado.obter_editavel(
            comunicado_canonico, g.turma_id, g.utilizador_id
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar o comunicado.",
            503,
        )

    if comunicado is None:
        return erro(
            "notice_not_editable",
            "O comunicado não existe ou não permite anexos por esta conta.",
            404,
        )

    if request.mimetype != "multipart/form-data":
        return erro(
            "unsupported_media_type",
            "Envia a fotografia como multipart/form-data.",
            415,
        )

    if (
        request.form
        or set(request.files) != {"fotografia"}
        or len(request.files.getlist("fotografia")) != 1
    ):
        return erro(
            "invalid_fields",
            "Envia apenas um ficheiro no campo fotografia.",
            400,
        )

    ficheiro = request.files["fotografia"]
    conteudo = ficheiro.stream.read(
        MAX_FOTOGRAFIA_BYTES + 1
    )

    if not conteudo:
        return erro(
            "empty_file",
            "A fotografia está vazia.",
            400,
        )

    if len(conteudo) > MAX_FOTOGRAFIA_BYTES:
        return erro(
            "file_too_large",
            "A fotografia deve ter até 5 MB.",
            413,
        )

    try:
        imagem_jpeg, largura, altura = preparar_fotografia(conteudo)

    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        OSError,
        ValueError,
        SyntaxError,
    ):
        return erro(
            "invalid_image",
            "Envia uma imagem JPEG, PNG ou WebP válida, "
            "não animada e com até 20 milhões de píxeis. "
            "A imagem convertida também deve caber em 5 MB.",
            400,
        )

    fotografia_id = ObjectId()
    nome_download = f"educonecta-{fotografia_id}.jpg"

    try:
        modelo_anexo.guardar_fotografia(
            fotografia_id,
            imagem_jpeg,
            nome_download,
            {
                "comunicado_id": comunicado_canonico,
                "turma_id": g.turma_id,
                "criado_por": g.utilizador_id,
                "tipo": "image/jpeg",
                "largura": largura,
                "altura": altura,
            },
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível confirmar o carregamento. "
            "Não repitas automaticamente o pedido.",
            503,
        )

    return jsonify({
        "id": str(fotografia_id),
        "comunicado_id": comunicado_canonico,
        "turma_id": g.turma_id,
        "nome": nome_download,
        "tipo": "image/jpeg",
        "tamanho_bytes": len(imagem_jpeg),
        "largura": largura,
        "altura": altura,
    }), 201
