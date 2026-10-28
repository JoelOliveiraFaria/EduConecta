import hashlib

from bson import ObjectId
from flask import Blueprint, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.conversa as modelo_conversa
from utils.acesso import obter_conta_chat, validar_relacao_chat
from utils.service_client import erro

bp = Blueprint("chat", __name__)


def obter_conversa_autorizada(conversa_id):
    conta, falha = obter_conta_chat()

    if falha is not None:
        return None, None, falha

    if (
        len(conversa_id) != 64
        or any(
            caractere not in "0123456789abcdef"
            for caractere in conversa_id
        )
    ):
        return None, None, erro(
            "invalid_conversation_id",
            "O identificador da conversa é inválido.",
            400,
        )

    conta_id = str(ObjectId(conta["id"]))

    campo_participante = (
        "profissional_utilizador_id"
        if conta["perfil"] in {"docente", "educadora"}
        else "encarregado_utilizador_id"
    )

    try:
        conversa = modelo_conversa.obter_conversa_participante(
            conversa_id, campo_participante, conta_id
        )

    except PyMongoError:
        return None, None, erro(
            "database_unavailable",
            "Não foi possível consultar a conversa.",
            503,
        )

    if conversa is None:
        return None, None, erro(
            "conversation_not_accessible",
            "A conversa não existe ou não está acessível.",
            404,
        )

    campos_contexto = (
        "aluno_id",
        "profissional_utilizador_id",
        "encarregado_utilizador_id",
    )

    if any(
        not isinstance(conversa.get(campo), str)
        or not ObjectId.is_valid(conversa[campo])
        for campo in campos_contexto
    ):
        return None, None, erro(
            "conversation_unavailable",
            "A conversa tem um contexto inválido.",
            503,
        )

    contexto = {
        campo: conversa[campo]
        for campo in campos_contexto
    }

    _, falha = validar_relacao_chat(conta, contexto)

    if falha is not None:
        return None, None, falha

    return conversa, conta, None


@bp.post("/conversas")
def criar_conversa():
    conta, falha = obter_conta_chat()

    if falha is not None:
        return falha

    if not request.is_json:
        return erro(
            "unsupported_media_type",
            "Envia Content-Type: application/json.",
            415,
        )

    dados = request.get_json(silent=True)

    campos = {
        "aluno_id",
        "profissional_utilizador_id",
        "encarregado_utilizador_id",
    }

    if (
        not isinstance(dados, dict)
        or set(dados) != campos
        or any(
            not isinstance(dados[campo], str)
            or not ObjectId.is_valid(dados[campo])
            for campo in campos
        )
    ):
        return erro(
            "invalid_fields",
            "Envia aluno_id, profissional_utilizador_id e "
            "encarregado_utilizador_id com identificadores válidos.",
            400,
        )

    contexto = {
        campo: str(ObjectId(dados[campo]))
        for campo in campos
    }

    validacao, falha = validar_relacao_chat(conta, contexto)

    if falha is not None:
        return falha

    chave = ":".join([
        contexto["aluno_id"],
        contexto["profissional_utilizador_id"],
        contexto["encarregado_utilizador_id"],
    ])

    conversa_id = hashlib.sha256(
        chave.encode("utf-8")
    ).hexdigest()

    try:
        documento = modelo_conversa.criar_conversa(conversa_id, contexto)
        criada = True

    except DuplicateKeyError:
        try:
            documento = modelo_conversa.obter_conversa_por_id(conversa_id)
        except PyMongoError:
            return erro(
                "database_unavailable",
                "Não foi possível consultar a conversa.",
                503,
            )

        if documento is None:
            return erro(
                "conversation_unavailable",
                "Não foi possível recuperar a conversa. Tenta novamente.",
                503,
            )

        if any(
            documento.get(campo) != contexto[campo]
            for campo in campos
        ):
            return erro(
                "conversation_conflict",
                "A conversa existente tem um contexto incompatível.",
                409,
            )

        criada = False

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível criar a conversa.",
            503,
        )

    return jsonify({
        "conversa": modelo_conversa.serializar_conversa(documento),
        "criada": criada,
    }), 201 if criada else 200


@bp.post("/conversas/<conversa_id>/mensagens")
def enviar_mensagem(conversa_id):
    conversa, conta, falha = obter_conversa_autorizada(
        conversa_id
    )

    if falha is not None:
        return falha

    if not request.is_json:
        return erro(
            "unsupported_media_type",
            "Envia Content-Type: application/json.",
            415,
        )

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict) or set(dados) != {"texto"}:
        return erro(
            "invalid_fields",
            "Envia apenas o campo obrigatório texto.",
            400,
        )

    texto = dados["texto"]

    if (
        not isinstance(texto, str)
        or not 1 <= len(texto.strip()) <= 5000
    ):
        return erro(
            "invalid_text",
            "A mensagem deve ter entre 1 e 5000 caracteres.",
            400,
        )

    conta_id = str(ObjectId(conta["id"]))

    try:
        documento = modelo_conversa.criar_mensagem(
            conversa["_id"], texto.strip(), conta_id
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível confirmar o envio da mensagem. "
            "Consulta a conversa antes de tentar novamente.",
            503,
        )

    return jsonify(
        modelo_conversa.serializar_mensagem(documento, conta_id)
    ), 201


@bp.get("/conversas/<conversa_id>/mensagens")
def listar_mensagens(conversa_id):
    conversa, conta, falha = obter_conversa_autorizada(
        conversa_id
    )

    if falha is not None:
        return falha

    if set(request.args) - {"antes_de"}:
        return erro(
            "invalid_query",
            "O único parâmetro permitido é antes_de.",
            400,
        )

    valores_cursor = request.args.getlist("antes_de")

    if len(valores_cursor) > 1:
        return erro(
            "invalid_cursor",
            "Envia apenas um valor para antes_de.",
            400,
        )

    filtro = {"conversa_id": conversa["_id"]}

    if valores_cursor:
        cursor = valores_cursor[0]

        if not ObjectId.is_valid(cursor):
            return erro(
                "invalid_cursor",
                "O cursor de paginação é inválido.",
                400,
            )

        filtro["_id"] = {"$lt": ObjectId(cursor)}

    limite = 30
    conta_id = str(ObjectId(conta["id"]))

    try:
        documentos = modelo_conversa.listar_mensagens(filtro, limite)

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar as mensagens.",
            503,
        )

    tem_mais = len(documentos) > limite
    pagina = documentos[:limite]

    proximo_cursor = (
        str(pagina[-1]["_id"])
        if tem_mais and pagina
        else None
    )

    mensagens = [
        modelo_conversa.serializar_mensagem(documento, conta_id)
        for documento in reversed(pagina)
    ]

    return jsonify({
        "conversa_id": conversa["_id"],
        "mensagens": mensagens,
        "quantidade": len(mensagens),
        "limite": limite,
        "tem_mais": tem_mais,
        "proximo_cursor": proximo_cursor,
    }), 200


@bp.get("/conversas")
def listar_conversas():
    conta, falha = obter_conta_chat()

    if falha is not None:
        return falha

    if set(request.args) - {"depois_de"}:
        return erro(
            "invalid_query",
            "O único parâmetro permitido é depois_de.",
            400,
        )

    valores_cursor = request.args.getlist("depois_de")

    if len(valores_cursor) > 1:
        return erro(
            "invalid_cursor",
            "Envia apenas um valor para depois_de.",
            400,
        )

    conta_id = str(ObjectId(conta["id"]))

    campo_participante = (
        "profissional_utilizador_id"
        if conta["perfil"] in {"docente", "educadora"}
        else "encarregado_utilizador_id"
    )

    filtro = {
        campo_participante: conta_id,
    }

    if valores_cursor:
        cursor = valores_cursor[0]

        if (
            len(cursor) != 64
            or any(
                caractere not in "0123456789abcdef"
                for caractere in cursor
            )
        ):
            return erro(
                "invalid_cursor",
                "O cursor de paginação é inválido.",
                400,
            )

        filtro["_id"] = {"$gt": cursor}

    limite = 10

    try:
        documentos = modelo_conversa.listar_conversas_participante(filtro, limite)

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar as conversas.",
            503,
        )

    tem_mais = len(documentos) > limite
    pagina = documentos[:limite]

    conversas = []

    campos_contexto = (
        "aluno_id",
        "profissional_utilizador_id",
        "encarregado_utilizador_id",
    )

    for documento in pagina:
        if any(
            not isinstance(documento.get(campo), str)
            or not ObjectId.is_valid(documento[campo])
            for campo in campos_contexto
        ):
            return erro(
                "conversation_unavailable",
                "Uma conversa tem um contexto inválido.",
                503,
            )

        contexto = {
            campo: documento[campo]
            for campo in campos_contexto
        }

        validacao, falha = validar_relacao_chat(
            conta,
            contexto,
        )

        if falha is not None:
            estado = falha[1]

            if estado in {403, 404}:
                continue

            return falha

        conversa = modelo_conversa.serializar_conversa(documento)

        conversa["turma_id"] = str(
            ObjectId(validacao["turma_id"])
        )

        conversa["meu_papel"] = (
            "profissional"
            if conta["perfil"] in {"docente", "educadora"}
            else "encarregado"
        )

        conversas.append(conversa)

    proximo_cursor = (
        pagina[-1]["_id"]
        if tem_mais and pagina
        else None
    )

    return jsonify({
        "conversas": conversas,
        "quantidade": len(conversas),
        "limite": limite,
        "tem_mais": tem_mais,
        "proximo_cursor": proximo_cursor,
    }), 200
