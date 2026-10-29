import hashlib
import subprocess
import tempfile
from io import BytesIO

from bson import ObjectId
from flask import Blueprint, jsonify, request, send_file
from gridfs.errors import CorruptGridFile, NoFile
from PIL import Image, UnidentifiedImageError
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.anexo as modelo_anexo
import models.conversa as modelo_conversa
from db import MAX_FOTOGRAFIA_BYTES, MAX_VIDEO_BYTES
from utils.acesso import obter_conta_chat, validar_relacao_chat
from utils.imagem import preparar_fotografia
from utils.service_client import erro
from utils.video import analisar_mp4

"""Controller: conversas e mensagens entre um profissional (docente/educadora)
e um encarregado de educação, sobre um aluno em concreto.

A autorização nunca confia só no `conversa_id` — toda vez que uma conversa
é acedida, a relação aluno/profissional/encarregado é revalidada contra o
serviço escolar (ver utils/acesso.validar_relacao_chat), para a conversa
deixar de ser acessível automaticamente se essa relação deixar de existir
(ex: aluno mudou de turma, profissional deixou de estar atribuído a ela).

Uma mensagem pode ser texto, fotografia ou vídeo (`tipo`) — fotografia e
vídeo reutilizam exatamente a mesma validação/conversão que os comunicados
já usavam para fotografias (Pillow) e vídeos (ffprobe), só que gravadas com
`metadata.conversa_id` em vez de `metadata.comunicado_id` nos buckets GridFS
partilhados (ver models/anexo.py).
"""

bp = Blueprint("chat", __name__)


def obter_conversa_autorizada(conversa_id):
    """Resolve uma conversa pelo id e confirma, em dois passos, que quem pede
    tem mesmo acesso a ela: (1) a conta é um dos dois participantes guardados
    no documento da conversa; (2) a relação continua válida agora, revalidada
    no escolar (não só "era válida quando a conversa foi criada").
    Devolve (conversa, conta, None) no sucesso, ou (None, None, erro) na falha.
    """
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
    """Cria (ou recupera, se já existir) a conversa entre um aluno, um
    profissional e um encarregado.

    O id da conversa é o SHA-256 dos três ids juntos — não um ObjectId
    aleatório — por isso pedir a conversa dos mesmos três participantes duas
    vezes dá sempre o mesmo id, e criar é naturalmente idempotente: se já
    existir (DuplicateKeyError), basta ir buscá-la e confirmar que o
    contexto bate certo, sem inserir duplicados nem precisar de uma consulta
    prévia "existe ou não existe" antes de cada criação.
    """
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
    """Envia uma mensagem de texto para uma conversa já validada."""
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
            conversa["_id"], conta_id, tipo="texto", texto=texto.strip()
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


@bp.post("/conversas/<conversa_id>/mensagens/fotografia")
def enviar_fotografia(conversa_id):
    """Envia uma mensagem de fotografia — mesma validação/conversão que
    comunicado_controller.anexar_fotografia (Pillow: reencode JPEG, remove
    EXIF, limite de píxeis e tamanho)."""
    conversa, conta, falha = obter_conversa_autorizada(conversa_id)

    if falha is not None:
        return falha

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
    conteudo = ficheiro.stream.read(MAX_FOTOGRAFIA_BYTES + 1)

    if not conteudo:
        return erro("empty_file", "A fotografia está vazia.", 400)

    if len(conteudo) > MAX_FOTOGRAFIA_BYTES:
        return erro("file_too_large", "A fotografia deve ter até 5 MB.", 413)

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

    conta_id = str(ObjectId(conta["id"]))
    fotografia_id = ObjectId()

    try:
        modelo_anexo.guardar_fotografia_mensagem(
            fotografia_id,
            imagem_jpeg,
            f"educonecta-{fotografia_id}.jpg",
            {
                "conversa_id": conversa["_id"],
                "criado_por": conta_id,
                "tipo": "image/jpeg",
                "largura": largura,
                "altura": altura,
            },
        )
        documento = modelo_conversa.criar_mensagem(
            conversa["_id"], conta_id, tipo="fotografia", anexo_id=fotografia_id
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível confirmar o envio da fotografia. "
            "Não repitas automaticamente o pedido.",
            503,
        )

    return jsonify(modelo_conversa.serializar_mensagem(documento, conta_id)), 201


@bp.post("/conversas/<conversa_id>/mensagens/video")
def enviar_video(conversa_id):
    """Envia uma mensagem de vídeo — mesma validação (ffprobe) e streaming
    para ficheiro temporário que o comunicado_controller usava antes de o
    vídeo deixar de ser anexo de comunicado."""
    conversa, conta, falha = obter_conversa_autorizada(conversa_id)

    if falha is not None:
        return falha

    if request.mimetype != "multipart/form-data":
        return erro("unsupported_media_type", "Envia multipart/form-data.", 415)

    if (
        request.form
        or set(request.files) != {"video"}
        or len(request.files.getlist("video")) != 1
    ):
        return erro("invalid_fields", "Envia apenas um ficheiro no campo video.", 400)

    conta_id = str(ObjectId(conta["id"]))

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
            video_id = ObjectId()

            try:
                modelo_anexo.guardar_video_mensagem(
                    tmp,
                    video_id,
                    f"educonecta-{video_id}.mp4",
                    {
                        "conversa_id": conversa["_id"],
                        "criado_por": conta_id,
                        "tipo": "video/mp4",
                        **info,
                    },
                )
                documento = modelo_conversa.criar_mensagem(
                    conversa["_id"], conta_id, tipo="video", anexo_id=video_id
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

    return jsonify(modelo_conversa.serializar_mensagem(documento, conta_id)), 201


@bp.get("/conversas/<conversa_id>/mensagens/<mensagem_id>/anexo")
def obter_anexo_mensagem(conversa_id, mensagem_id):
    """Descarrega o anexo (fotografia ou vídeo) de uma mensagem."""
    conversa, conta, falha = obter_conversa_autorizada(conversa_id)

    if falha is not None:
        return falha

    try:
        mensagem = modelo_conversa.obter_mensagem(conversa["_id"], mensagem_id)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar a mensagem.", 503)

    if mensagem is None or mensagem.get("tipo") not in {"fotografia", "video"}:
        return erro("attachment_not_accessible", "Esta mensagem não tem anexo.", 404)

    tipo_bucket = "fotografias" if mensagem["tipo"] == "fotografia" else "videos"
    limite = MAX_FOTOGRAFIA_BYTES if tipo_bucket == "fotografias" else MAX_VIDEO_BYTES

    try:
        ficheiro = modelo_anexo.obter_anexo_mensagem(
            tipo_bucket, mensagem["anexo_id"], conversa["_id"]
        )

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

    extensao = "jpg" if tipo_bucket == "fotografias" else "mp4"
    resposta = send_file(
        BytesIO(dados),
        mimetype="image/jpeg" if tipo_bucket == "fotografias" else "video/mp4",
        download_name=f"educonecta-{mensagem['anexo_id']}.{extensao}",
        as_attachment=request.args.get("download") == "1",
        conditional=True, etag=False, max_age=0,
    )
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


@bp.get("/conversas/<conversa_id>/mensagens")
def listar_mensagens(conversa_id):
    """Lista mensagens de uma conversa (mais recentes primeiro, paginadas por
    cursor `antes_de`), devolvidas já por ordem cronológica (reversed)."""
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
    """Lista as conversas em que a conta autenticada participa.

    Cada conversa listada é revalidada individualmente contra o escolar
    (validar_relacao_chat) antes de entrar na resposta — uma conversa cuja
    relação já não é válida (403/404) é simplesmente omitida da lista em vez
    de rebentar o pedido todo; só uma falha de infraestrutura (503) aborta.
    """
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
