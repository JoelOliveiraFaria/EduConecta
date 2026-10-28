import json
import math
import os
import subprocess
import tempfile

from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bson import ObjectId
from flask import Flask, g, jsonify, request
from gridfs import GridFS
from PIL import Image, ImageOps, UnidentifiedImageError
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import RequestEntityTooLarge


app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 26 * 1024 * 1024


database_name = os.environ["MONGO_COMUNICADOS_DATABASE"]


client = MongoClient(
    host=os.environ["MONGO_HOST"],
    port=int(os.environ.get("MONGO_PORT", "27017")),
    username=os.environ["MONGO_COMUNICADOS_USERNAME"],
    password=os.environ["MONGO_COMUNICADOS_PASSWORD"],
    authSource=database_name,
    tz_aware=True,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
    socketTimeoutMS=3000,
)


database = client[database_name]


fotografias = GridFS(database, collection="fotografias")
videos = GridFS(database, collection="videos")


MAX_FOTOGRAFIA_BYTES = 5 * 1024 * 1024
MAX_FOTOGRAFIA_PIXEIS = 20_000_000
FORMATOS_FOTOGRAFIA = {"JPEG", "PNG", "WEBP"}

MAX_VIDEO_BYTES = 25 * 1024 * 1024


AUTH_URL = "http://auth:8000"
SCHOOL_URL = "http://escolar:8000"
PERFIS_PUBLICACAO = {"docente", "educadora"}


def erro(codigo, mensagem, estado):
    resposta = jsonify({
        "error": codigo,
        "message": mensagem,
    })

    if estado == 401:
        resposta.headers["WWW-Authenticate"] = "Bearer"

    return resposta, estado


def consultar_servico(url, metodo="GET", dados=None):
    headers = {
        "Authorization": request.headers.get("Authorization", ""),
        "Accept": "application/json",
    }

    corpo = None

    if dados is not None:
        headers["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode("utf-8")

    pedido = Request(
        url,
        data=corpo,
        headers=headers,
        method=metodo,
    )

    try:
        with urlopen(pedido, timeout=5) as resposta:
            dados = json.load(resposta)

        if not isinstance(dados, dict):
            raise ValueError("Resposta inesperada.")

        return dados, None

    except HTTPError as exc:
        if exc.code == 401:
            return None, erro(
                "authentication_required",
                "Sessão inválida ou expirada.",
                401,
            )

        if exc.code == 403:
            return None, erro(
                "forbidden",
                "A conta não tem autorização para esta operação.",
                403,
            )

        if exc.code == 404:
            return None, erro(
                "resource_not_accessible",
                "O recurso não existe ou não está acessível.",
                404,
            )

        return None, erro(
            "dependency_unavailable",
            "Não foi possível validar o acesso.",
            503,
        )

    except (URLError, TimeoutError, OSError, ValueError):
        return None, erro(
            "dependency_unavailable",
            "Não foi possível contactar os serviços de acesso.",
            503,
        )


def verificar_acesso(turma_id, publicar=False):
    if not ObjectId.is_valid(turma_id):
        return erro(
            "invalid_class_id",
            "O identificador da turma é inválido.",
            400,
        )

    turma_canonica = str(ObjectId(turma_id))

    conta, falha = consultar_servico(f"{AUTH_URL}/me")

    if falha is not None:
        return falha

    if (
        conta.get("estado") != "ativo"
        or not isinstance(conta.get("id"), str)
        or not ObjectId.is_valid(conta["id"])
    ):
        return erro(
            "invalid_session",
            "Não foi possível validar a conta.",
            401,
        )

    perfil = conta.get("perfil")

    if perfil in PERFIS_PUBLICACAO:
        dados, falha = consultar_servico(
            f"{SCHOOL_URL}/me/turmas/{turma_canonica}/alunos"
        )

        if falha is not None:
            return falha

        if not isinstance(dados.get("alunos"), list):
            return erro(
                "dependency_unavailable",
                "O serviço escolar devolveu uma resposta inesperada.",
                503,
            )

    elif perfil == "encarregado" and not publicar:
        dados, falha = consultar_servico(
            f"{SCHOOL_URL}/me/alunos"
        )

        if falha is not None:
            return falha

        alunos = dados.get("alunos")

        if not isinstance(alunos, list):
            return erro(
                "dependency_unavailable",
                "O serviço escolar devolveu uma resposta inesperada.",
                503,
            )

        associado = any(
            isinstance(aluno, dict)
            and isinstance(aluno.get("turma_id"), str)
            and ObjectId.is_valid(aluno["turma_id"])
            and str(ObjectId(aluno["turma_id"])) == turma_canonica
            for aluno in alunos
        )

        if not associado:
            return erro(
                "class_not_accessible",
                "A turma não existe ou não está associada aos teus educandos.",
                404,
            )

    else:
        return erro(
            "forbidden",
            "O teu perfil não pode realizar esta operação.",
            403,
        )

    g.utilizador_id = str(ObjectId(conta["id"]))
    g.turma_id = turma_canonica
    return None


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


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "comunicados",
        "application": "EduConecta",
    }), 200


@app.get("/ready")
def ready():
    try:
        database.list_collection_names()

    except PyMongoError:
        return erro(
            "database_unavailable",
            "A base de dados dos Comunicados não está disponível.",
            503,
        )

    return jsonify({
        "status": "ready",
        "service": "comunicados",
        "database": "connected",
    }), 200


@app.post("/turmas/<turma_id>/comunicados")
def publicar_comunicado(turma_id):
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

    documento = {
        "_id": ObjectId(),
        "turma_id": g.turma_id,
        "titulo": titulo.strip(),
        "texto": texto.strip(),
        "criado_por": g.utilizador_id,
        "criado_em": datetime.now(timezone.utc),
    }

    try:
        database["comunicados"].insert_one(documento)

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível guardar o comunicado.",
            503,
        )

    return jsonify(serializar(documento)), 201


@app.get("/turmas/<turma_id>/comunicados")
def listar_comunicados(turma_id):
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
        documentos = list(
            database["comunicados"]
            .find({"turma_id": g.turma_id})
            .sort([("criado_em", -1), ("_id", -1)])
            .skip((pagina - 1) * limite)
            .limit(limite + 1)
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar os comunicados.",
            503,
        )

    tem_mais = len(documentos) > limite

    comunicados = [
        serializar(documento)
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


@app.after_request
def impedir_cache(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def obter_conta_chat():
    conta, falha = consultar_servico(f"{AUTH_URL}/me")

    if falha is not None:
        return None, falha

    if (
        conta.get("estado") != "ativo"
        or not isinstance(conta.get("id"), str)
        or not ObjectId.is_valid(conta["id"])
        or conta.get("perfil") not in {
            "docente",
            "educadora",
            "encarregado",
        }
    ):
        return None, erro(
            "forbidden",
            "Esta operação exige uma conta autorizada para o chat.",
            403,
        )

    return conta, None


def validar_relacao_chat(conta, contexto):
    if conta["perfil"] in {"docente", "educadora"}:
        participante = contexto["profissional_utilizador_id"]
    else:
        participante = contexto["encarregado_utilizador_id"]

    if str(ObjectId(conta["id"])) != participante:
        return None, erro(
            "forbidden",
            "Só podes aceder a conversas em que participas.",
            403,
        )

    validacao, falha = consultar_servico(
        f"{SCHOOL_URL}/me/chat/validar",
        metodo="POST",
        dados=contexto,
    )

    if falha is not None:
        return None, falha

    if (
        validacao.get("autorizado") is not True
        or any(
            validacao.get(campo) != contexto[campo]
            for campo in contexto
        )
        or not isinstance(validacao.get("turma_id"), str)
        or not ObjectId.is_valid(validacao["turma_id"])
    ):
        return None, erro(
            "dependency_unavailable",
            "O serviço escolar devolveu uma validação inesperada.",
            503,
        )

    return validacao, None


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


@app.post("/conversas")
def criar_conversa():
    import hashlib

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

    documento = {
        "_id": conversa_id,
        **contexto,
        "criado_em": datetime.now(timezone.utc),
    }

    try:
        database["conversas"].insert_one(documento)
        criada = True

    except DuplicateKeyError:
        try:
            documento = database["conversas"].find_one(
                {"_id": conversa_id}
            )
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
        "conversa": serializar_conversa(documento),
        "criada": criada,
    }), 201 if criada else 200


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
        conversa = database["conversas"].find_one({
            "_id": conversa_id,
            campo_participante: conta_id,
        })

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


@app.post("/conversas/<conversa_id>/mensagens")
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

    documento = {
        "_id": ObjectId(),
        "conversa_id": conversa["_id"],
        "texto": texto.strip(),
        "enviado_por": conta_id,
        "criado_em": datetime.now(timezone.utc),
    }

    try:
        database["mensagens"].insert_one(documento)

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível confirmar o envio da mensagem. "
            "Consulta a conversa antes de tentar novamente.",
            503,
        )

    return jsonify(
        serializar_mensagem(documento, conta_id)
    ), 201


@app.get("/conversas/<conversa_id>/mensagens")
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
        documentos = list(
            database["mensagens"]
            .find(filtro)
            .sort("_id", -1)
            .limit(limite + 1)
        )

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
        serializar_mensagem(documento, conta_id)
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


@app.get("/conversas")
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
        documentos = list(
            database["conversas"]
            .find(filtro)
            .sort("_id", 1)
            .limit(limite + 1)
        )

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

        conversa = serializar_conversa(documento)

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

@app.errorhandler(RequestEntityTooLarge)
def pedido_demasiado_grande(_erro):
    return erro(
        "request_too_large",
        "O pedido excede o tamanho permitido.",
        413,
    )


def preparar_fotografia(conteudo):
    with Image.open(BytesIO(conteudo)) as imagem:
        if imagem.format not in FORMATOS_FOTOGRAFIA:
            raise ValueError("Formato não permitido.")

        largura, altura = imagem.size

        if (
            largura <= 0
            or altura <= 0
            or largura * altura > MAX_FOTOGRAFIA_PIXEIS
        ):
            raise ValueError("Dimensões não permitidas.")

        if getattr(imagem, "is_animated", False):
            raise ValueError("Imagens animadas não são permitidas.")

        imagem.load()
        orientada = ImageOps.exif_transpose(imagem)

        try:
            rgba = orientada.convert("RGBA")

            try:
                limpa = Image.new("RGB", rgba.size, "white")

                try:
                    mascara = rgba.getchannel("A")

                    try:
                        limpa.paste(rgba, mask=mascara)
                    finally:
                        mascara.close()

                    with BytesIO() as saida:
                        limpa.save(
                            saida,
                            format="JPEG",
                            quality=90,
                        )
                        resultado = saida.getvalue()

                    largura, altura = limpa.size

                finally:
                    limpa.close()

            finally:
                rgba.close()

        finally:
            orientada.close()

    if len(resultado) > MAX_FOTOGRAFIA_BYTES:
        raise ValueError("Imagem convertida demasiado grande.")

    return resultado, largura, altura


@app.post(
    "/turmas/<turma_id>/comunicados/"
    "<comunicado_id>/fotografias"
)
def anexar_fotografia(turma_id, comunicado_id):
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
        comunicado = database["comunicados"].find_one(
            {
                "_id": ObjectId(comunicado_canonico),
                "turma_id": g.turma_id,
                "criado_por": g.utilizador_id,
            },
            {"_id": 1},
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
        imagem_jpeg, largura, altura = preparar_fotografia(
            conteudo
        )

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
        fotografias.put(
            imagem_jpeg,
            _id=fotografia_id,
            filename=nome_download,
            metadata={
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

from anexos import instalar_anexos

instalar_anexos(app, database, verificar_acesso, erro)