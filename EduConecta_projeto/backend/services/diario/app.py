import json
import os

from datetime import date, datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bson import ObjectId
from flask import Flask, g, jsonify, request
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError


app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

database_name = os.environ["MONGO_DIARIO_DATABASE"]

client = MongoClient(
    host=os.environ["MONGO_HOST"],
    port=int(os.environ.get("MONGO_PORT", "27017")),
    username=os.environ["MONGO_DIARIO_USERNAME"],
    password=os.environ["MONGO_DIARIO_PASSWORD"],
    authSource=database_name, 
    tz_aware=True,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
    socketTimeoutMS=3000,
)

database = client[database_name]

AUTH_URL = "http://auth:8000"
SCHOOL_URL = "http://escolar:8000"

CAMPOS_TEXTO = (
    "alimentacao",
    "sono",
    "higiene",
    "atividades",
    "observacoes",
)


def erro(codigo, mensagem, estado):
    resposta = jsonify({
        "error": codigo,
        "message": mensagem,
    })

    if estado == 401:
        resposta.headers["WWW-Authenticate"] = "Bearer"

    return resposta, estado


def consultar_servico(url):
    pedido = Request(
        url,
        headers={
            "Authorization": request.headers.get("Authorization", ""),
            "Accept": "application/json",
        },
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
                "Sessão inválida ou expirada. Inicia sessão novamente.",
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
            "Não foi possível validar o acesso. Tenta novamente.",
            503,
        )

    except (URLError, TimeoutError, OSError, ValueError):
        return None, erro(
            "dependency_unavailable",
            "Não foi possível contactar os serviços de acesso.",
            503,
        )


def verificar_acesso(turma_id, aluno_id):
    if not ObjectId.is_valid(turma_id):
        return erro(
            "invalid_class_id",
            "O identificador da turma é inválido.",
            400,
        )

    if not ObjectId.is_valid(aluno_id):
        return erro(
            "invalid_student_id",
            "O identificador do aluno é inválido.",
            400,
        )

    conta, falha = consultar_servico(f"{AUTH_URL}/me")

    if falha is not None:
        return falha

    if (
        conta.get("estado") != "ativo"
        or conta.get("perfil") not in {"docente", "educadora", "auxiliar"}
        or not isinstance(conta.get("id"), str)
        or not ObjectId.is_valid(conta["id"])
    ):
        return erro(
            "forbidden",
            "Esta operação exige uma conta profissional ativa.",
            403,
        )

    dados, falha = consultar_servico(
        f"{SCHOOL_URL}/me/turmas/{turma_id}/alunos"
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

    aluno_canonico = str(ObjectId(aluno_id))

    if not any(
        isinstance(aluno, dict)
        and aluno.get("id") == aluno_canonico
        for aluno in alunos
    ):
        return erro(
            "student_not_accessible",
            "O aluno não foi encontrado entre os alunos acessíveis da turma.",
            404,
        )

    g.utilizador_id = conta["id"]
    return None


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


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "diario",
        "application": "EduConecta",
    }), 200


@app.get("/ready")
def ready():
    try:
        database.list_collection_names()
    except PyMongoError:
        return erro(
            "database_unavailable",
            "A base de dados do Diário não está disponível.",
            503,
        )

    return jsonify({
        "status": "ready",
        "service": "diario",
        "database": "connected",
    }), 200


@app.post("/turmas/<turma_id>/alunos/<aluno_id>/diario")
def criar_registo(turma_id, aluno_id):
    falha = verificar_acesso(turma_id, aluno_id)

    if falha is not None:
        return falha

    if not request.is_json:
        return erro(
            "unsupported_media_type",
            "Envia Content-Type: application/json.",
            415,
        )

    dados = request.get_json(silent=True)
    campos = {"data", *CAMPOS_TEXTO}

    if not isinstance(dados, dict) or set(dados) != campos:
        return erro(
            "invalid_fields",
            "Envia apenas data, alimentacao, sono, higiene, "
            "atividades e observacoes. Todos os campos são obrigatórios.",
            400,
        )

    data_texto = dados["data"]

    try:
        if not isinstance(data_texto, str):
            raise ValueError

        data_registo = date.fromisoformat(data_texto)

        if data_registo.isoformat() != data_texto:
            raise ValueError

    except ValueError:
        return erro(
            "invalid_date",
            "A data deve ter o formato AAAA-MM-DD e ser válida.",
            400,
        )

    textos = {}

    for campo in CAMPOS_TEXTO:
        valor = dados[campo]

        if not isinstance(valor, str) or len(valor) > 2000:
            return erro(
                "invalid_text",
                f"O campo {campo} deve ser texto com até 2000 caracteres.",
                400,
            )

        textos[campo] = valor.strip()

    if not any(textos.values()):
        return erro(
            "empty_record",
            "Preenche pelo menos um dos campos do Diário.",
            400,
        )

    aluno_canonico = str(ObjectId(aluno_id))
    turma_canonica = str(ObjectId(turma_id))

    documento = {
        "_id": f"{aluno_canonico}:{data_texto}",
        "aluno_id": aluno_canonico,
        "turma_id": turma_canonica,
        "data": data_texto,
        **textos,
        "criado_por": g.utilizador_id,
        "criado_em": datetime.now(timezone.utc),
    }

    try:
        database["registos"].insert_one(documento)

    except DuplicateKeyError:
        return erro(
            "daily_record_already_exists",
            "Já existe um registo para este aluno nesta data.",
            409,
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível guardar o registo.",
            503,
        )

    return jsonify(serializar(documento)), 201


@app.get("/turmas/<turma_id>/alunos/<aluno_id>/diario")
def listar_registos(turma_id, aluno_id):
    falha = verificar_acesso(turma_id, aluno_id)

    if falha is not None:
        return falha

    try:
        documentos = (
            database["registos"]
            .find({
                "aluno_id": str(ObjectId(aluno_id)),
                "turma_id": str(ObjectId(turma_id)),
            })
            .sort("data", -1)
            .limit(31)
        )

        registos = [
            serializar(documento)
            for documento in documentos
        ]

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar os registos.",
            503,
        )

    return jsonify({
        "registos": registos,
        "quantidade": len(registos),
        "limite": 31,
    }), 200


@app.after_request
def impedir_cache(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    return resposta

@app.get("/me/alunos/<aluno_id>/diario")
def listar_diario_meu_educando(aluno_id):
    if not ObjectId.is_valid(aluno_id):
        return erro(
            "invalid_student_id",
            "O identificador do aluno é inválido.",
            400,
        )

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

    if conta.get("perfil") != "encarregado":
        return erro(
            "forbidden",
            "Esta consulta destina-se a encarregados de educação.",
            403,
        )

    dados, falha = consultar_servico(f"{SCHOOL_URL}/me/alunos")

    if falha is not None:
        return falha

    alunos = dados.get("alunos")

    if not isinstance(alunos, list):
        return erro(
            "dependency_unavailable",
            "O serviço escolar devolveu uma resposta inesperada.",
            503,
        )

    aluno_canonico = str(ObjectId(aluno_id))

    aluno = next(
        (
            item
            for item in alunos
            if isinstance(item, dict)
            and item.get("id") == aluno_canonico
        ),
        None,
    )

    if aluno is None:
        return erro(
            "student_not_accessible",
            "O aluno não existe ou não está associado à tua conta.",
            404,
        )

    turma_id = aluno.get("turma_id")

    if not isinstance(turma_id, str) or not ObjectId.is_valid(turma_id):
        return erro(
            "student_class_not_linked",
            "O aluno ainda não tem uma turma válida associada.",
            404,
        )

    try:
        documentos = (
            database["registos"]
            .find({
                "aluno_id": aluno_canonico,
                "turma_id": str(ObjectId(turma_id)),
            })
            .sort("data", -1)
            .limit(31)
        )

        registos = []

        for documento in documentos:
            registo = serializar(documento)
            registo.pop("criado_por", None)
            registos.append(registo)

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar o Diário do educando.",
            503,
        )

    return jsonify({
        "aluno": {
            "id": aluno_canonico,
            "nome": aluno.get("nome"),
            "turma_id": str(ObjectId(turma_id)),
        },
        "registos": registos,
        "quantidade": len(registos),
        "limite": 31,
    }), 200

@app.patch("/turmas/<turma_id>/alunos/<aluno_id>/diario/<data_registo>")
def editar_registo(turma_id, aluno_id, data_registo):
    from pymongo import ReturnDocument

    falha = verificar_acesso(turma_id, aluno_id)

    if falha is not None:
        return falha

    try:
        data_validada = date.fromisoformat(data_registo)

        if data_validada.isoformat() != data_registo:
            raise ValueError

    except ValueError:
        return erro(
            "invalid_date",
            "A data deve ter o formato AAAA-MM-DD e ser válida.",
            400,
        )

    if not request.is_json:
        return erro(
            "unsupported_media_type",
            "Envia Content-Type: application/json.",
            415,
        )

    dados = request.get_json(silent=True)

    if (
        not isinstance(dados, dict)
        or not dados
        or set(dados) - set(CAMPOS_TEXTO)
    ):
        return erro(
            "invalid_fields",
            "Envia um ou mais campos: alimentacao, sono, "
            "higiene, atividades e observacoes.",
            400,
        )

    alteracoes = {}

    for campo, valor in dados.items():
        if not isinstance(valor, str) or len(valor) > 2000:
            return erro(
                "invalid_text",
                f"O campo {campo} deve ser texto com até 2000 caracteres.",
                400,
            )

        alteracoes[campo] = valor.strip()

    if not any(alteracoes.values()):
        return erro(
            "empty_update",
            "Inclui pelo menos um campo com texto nesta edição.",
            400,
        )

    aluno_canonico = str(ObjectId(aluno_id))

    alteracoes["atualizado_em"] = datetime.now(timezone.utc)
    alteracoes["atualizado_por"] = g.utilizador_id

    try:
        documento = database["registos"].find_one_and_update(
            {
                "_id": f"{aluno_canonico}:{data_registo}",
                "aluno_id": aluno_canonico,
                "turma_id": str(ObjectId(turma_id)),
                "criado_por": g.utilizador_id,
            },
            {"$set": alteracoes},
            return_document=ReturnDocument.AFTER,
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível atualizar o registo.",
            503,
        )

    if documento is None:
        return erro(
            "record_not_editable",
            "O registo não existe ou não pode ser editado por esta conta.",
            404,
        )

    resposta = serializar(documento)
    resposta["atualizado_em"] = documento["atualizado_em"].isoformat(
        timespec="milliseconds"
    )
    resposta["atualizado_por"] = documento["atualizado_por"]

    return jsonify(resposta), 200