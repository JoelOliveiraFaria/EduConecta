import json
import os
from datetime import date, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bson import ObjectId
from flask import Flask, g, jsonify, request
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from werkzeug.exceptions import RequestEntityTooLarge

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
nome_bd = os.environ["MONGO_ASSIDUIDADE_DATABASE"]
client = MongoClient(
    host=os.environ.get("MONGO_HOST", "mongo-school"),
    port=int(os.environ.get("MONGO_PORT", "27017")),
    username=os.environ["MONGO_ASSIDUIDADE_USERNAME"],
    password=os.environ["MONGO_ASSIDUIDADE_PASSWORD"],
    authSource=nome_bd, tz_aware=True,
    serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=3000,
)
database = client[nome_bd]
registos = database["assiduidade"]
ESTADOS = {"presente", "falta", "por_marcar"}


def erro(codigo, mensagem, estado):
    resposta = jsonify({"error": codigo, "message": mensagem})
    if estado == 401:
        resposta.headers["WWW-Authenticate"] = "Bearer"
    return resposta, estado


def consultar(url):
    pedido = Request(url, headers={
        "Authorization": request.headers.get("Authorization", ""),
        "Accept": "application/json",
    })
    try:
        with urlopen(pedido, timeout=5) as resposta:
            dados = json.load(resposta)
        if not isinstance(dados, dict):
            raise ValueError()
        return dados, None
    except HTTPError as exc:
        codigo = exc.code
        exc.close()
        if codigo == 401:
            return None, erro("authentication_required", "Sessão inválida ou expirada.", 401)
        if codigo in {403, 404}:
            return None, erro("resource_not_accessible", "Recurso não acessível.", codigo)
        return None, erro("dependency_unavailable", "Serviço de acesso indisponível.", 503)
    except (URLError, OSError, TimeoutError, ValueError):
        return None, erro("dependency_unavailable", "Não foi possível validar o acesso.", 503)


@app.before_request
def autenticar():
    if request.endpoint is None or request.endpoint in {"health", "ready"}:
        return None
    h = request.headers.get("Authorization", "")
    partes = h.split()
    if len(h) > 8192 or len(partes) != 2 or partes[0].lower() != "bearer":
        return erro("authentication_required", "É necessário iniciar sessão.", 401)
    conta, falha = consultar("http://auth:8000/me")
    if falha is not None:
        return falha
    if (conta.get("estado") != "ativo" or not isinstance(conta.get("id"), str)
            or not ObjectId.is_valid(conta["id"])):
        return erro("invalid_session", "Sessão inválida.", 401)
    permissoes = {
        "consultar_turma": {"docente", "educadora"},
        "marcar": {"docente", "educadora"},
        "consultar_educando": {"encarregado"},
    }
    if conta.get("perfil") not in permissoes.get(request.endpoint, set()):
        return erro("forbidden", "O teu perfil não pode realizar esta operação.", 403)
    g.conta_id = str(ObjectId(conta["id"]))


@app.after_request
def sem_cache(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


@app.errorhandler(RequestEntityTooLarge)
def pedido_grande(_exc):
    return erro("request_too_large", "Pedido demasiado grande.", 413)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "assiduidade"}), 200


@app.get("/ready")
def ready():
    try:
        database.list_collection_names()
    except PyMongoError:
        return erro("database_unavailable", "Base de dados indisponível.", 503)
    return jsonify({"status": "ready", "service": "assiduidade", "database": "connected"}), 200


def data_iso(valor):
    if not isinstance(valor, str):
        raise ValueError()
    dia = date.fromisoformat(valor)
    if dia.isoformat() != valor:
        raise ValueError()
    return dia


def alunos_autorizados(turma_id):
    if not ObjectId.is_valid(turma_id):
        return None, None, erro("invalid_class_id", "Identificador de turma inválido.", 400)
    tid = str(ObjectId(turma_id))
    dados, falha = consultar(f"http://escolar:8000/me/turmas/{tid}/alunos")
    if falha is not None:
        return None, None, falha
    alunos = dados.get("alunos")
    turma = dados.get("turma")
    quantidade = dados.get("quantidade")
    limite = dados.get("limite")
    if (not isinstance(alunos, list) or not isinstance(turma, dict)
            or turma.get("id") != tid or type(quantidade) is not int
            or quantidade != len(alunos) or type(limite) is not int
            or limite <= 0 or any(not isinstance(a, dict)
            or not isinstance(a.get("id"), str) or not ObjectId.is_valid(a["id"])
            or a.get("turma_id") != tid for a in alunos)):
        return None, None, erro("dependency_unavailable", "Resposta escolar inesperada.", 503)
    if len(alunos) >= limite:
        return None, None, erro("school_list_limit", "A lista escolar atingiu o limite; não é possível garantir que esteja completa.", 409)
    return tid, alunos, None


def serializar(doc, aluno_id, dia, profissional=False):
    item = {"aluno_id": aluno_id, "data": dia,
            "estado": doc["estado"] if doc else "por_marcar",
            "versao": doc["versao"] if doc else 0,
            "atualizado_em": doc["atualizado_em"].isoformat(timespec="milliseconds") if doc else None}
    if doc:
        item["turma_id"] = doc["turma_id"]
    if profissional:
        item["atualizado_por"] = doc["atualizado_por"] if doc else None
    return item


@app.get("/turmas/<turma_id>/assiduidade")
def consultar_turma(turma_id):
    if set(request.args) != {"data"} or len(request.args.getlist("data")) != 1:
        return erro("invalid_query", "Envia apenas data=AAAA-MM-DD.", 400)
    try:
        dia = data_iso(request.args["data"]).isoformat()
    except ValueError:
        return erro("invalid_date", "Data inválida; usa AAAA-MM-DD.", 400)
    tid, alunos, falha = alunos_autorizados(turma_id)
    if falha is not None:
        return falha
    ids = [str(ObjectId(a["id"])) for a in alunos]
    try:
        docs = {d["aluno_id"]: d for d in registos.find({"data": dia, "aluno_id": {"$in": ids}})}
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar as marcações.", 503)
    itens = []
    contagem = {e: 0 for e in sorted(ESTADOS)}
    for aluno, aid in zip(alunos, ids):
        doc = docs.get(aid)
        item = serializar(doc, aid, dia, profissional=True)
        item["nome"] = aluno.get("nome")
        item["editavel"] = doc is None or doc["turma_id"] == tid
        contagem[item["estado"]] += 1
        itens.append(item)
    return jsonify({"turma_id": tid, "data": dia, "alunos": itens,
                    "quantidade": len(itens), "contagem": contagem}), 200


@app.put("/turmas/<turma_id>/alunos/<aluno_id>/assiduidade/<dia>")
def marcar(turma_id, aluno_id, dia):
    if not ObjectId.is_valid(aluno_id):
        return erro("invalid_student_id", "Identificador de aluno inválido.", 400)
    aid = str(ObjectId(aluno_id))
    try:
        dia = data_iso(dia).isoformat()
    except ValueError:
        return erro("invalid_date", "Data inválida; usa AAAA-MM-DD.", 400)
    if request.args:
        return erro("invalid_query", "Esta operação não aceita parâmetros de pesquisa.", 400)
    if not request.is_json:
        return erro("unsupported_media_type", "Envia application/json.", 415)
    dados = request.get_json(silent=True)
    if (not isinstance(dados, dict) or set(dados) != {"estado", "versao"}
            or not isinstance(dados.get("estado"), str) or dados["estado"] not in ESTADOS
            or type(dados.get("versao")) is not int or not 0 <= dados["versao"] < 2**31):
        return erro("invalid_fields", "Envia estado (presente, falta ou por_marcar) e versao inteira não negativa.", 400)
    tid, alunos, falha = alunos_autorizados(turma_id)
    if falha is not None:
        return falha
    if not any(str(ObjectId(a["id"])) == aid for a in alunos):
        return erro("student_not_accessible", "Aluno não pertence à turma acessível.", 404)
    agora = datetime.now(timezone.utc)
    try:
        doc = registos.find_one_and_update(
            {"_id": f"{aid}:{dia}", "turma_id": tid, "versao": dados["versao"]},
            {"$set": {"estado": dados["estado"], "atualizado_em": agora,
                      "atualizado_por": g.conta_id},
             "$setOnInsert": {"aluno_id": aid, "data": dia, "criado_em": agora},
             "$inc": {"versao": 1}},
            upsert=dados["versao"] == 0, return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        return erro("attendance_conflict", "A marcação mudou ou pertence a outra turma. Atualiza a consulta.", 409)
    except PyMongoError:
        return erro("database_unavailable", "Gravação não confirmada. Consulta antes de repetir.", 503)
    if doc is None:
        return erro("attendance_conflict", "A marcação mudou. Atualiza a consulta.", 409)
    return jsonify(serializar(doc, aid, dia, profissional=True)), 200


@app.get("/alunos/<aluno_id>/assiduidade")
def consultar_educando(aluno_id):
    if not ObjectId.is_valid(aluno_id):
        return erro("invalid_student_id", "Identificador de aluno inválido.", 400)
    aid = str(ObjectId(aluno_id))
    if (set(request.args) != {"inicio", "fim"}
            or any(len(request.args.getlist(c)) != 1 for c in ("inicio", "fim"))):
        return erro("invalid_query", "Envia inicio e fim no formato AAAA-MM-DD.", 400)
    try:
        inicio = data_iso(request.args["inicio"])
        fim = data_iso(request.args["fim"])
        if not 0 <= (fim - inicio).days <= 30:
            raise ValueError()
    except ValueError:
        return erro("invalid_date_range", "Intervalo inválido; máximo de 31 dias inclusive.", 400)
    dados, falha = consultar("http://escolar:8000/me/alunos")
    if falha is not None:
        return falha
    alunos = dados.get("alunos")
    if (not isinstance(alunos, list) or any(not isinstance(a, dict)
            or not isinstance(a.get("id"), str) or not ObjectId.is_valid(a["id"])
            for a in alunos)):
        return erro("dependency_unavailable", "Resposta escolar inesperada.", 503)
    if not any(str(ObjectId(a["id"])) == aid for a in alunos):
        if type(dados.get("limite")) is int and len(alunos) >= dados["limite"]:
            return erro("school_list_limit", "A lista escolar pode estar incompleta.", 409)
        return erro("student_not_accessible", "Educando não acessível.", 404)
    try:
        docs = {d["data"]: d for d in registos.find({
            "aluno_id": aid, "data": {"$gte": inicio.isoformat(), "$lte": fim.isoformat()},
        })}
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar as marcações.", 503)
    itens = []
    for deslocamento in range((fim - inicio).days + 1):
        texto = (inicio + timedelta(days=deslocamento)).isoformat()
        itens.append(serializar(docs.get(texto), aid, texto))
    return jsonify({"aluno_id": aid, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
                    "registos": itens, "quantidade": len(itens)}), 200