import os
import jwt
import secrets


from flask import Flask, jsonify, request
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from datetime import datetime, timedelta, timezone

from email_validator import EmailNotValidError, validate_email
from werkzeug.security import check_password_hash, generate_password_hash
from bson import ObjectId

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

database_name = os.environ["MONGO_AUTH_DATABASE"]

client = MongoClient(
    host=os.environ["MONGO_HOST"],
    port=int(os.environ.get("MONGO_PORT", "27017")),
    username=os.environ["MONGO_AUTH_USERNAME"],
    password=os.environ["MONGO_AUTH_PASSWORD"],
    authSource=database_name,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
    socketTimeoutMS=3000,
)

database = client[database_name]

jwt_secret = os.environ["JWT_SECRET_KEY"]

if len(jwt_secret) < 32:
    raise RuntimeError("A chave JWT deve ter pelo menos 32 caracteres.")

dummy_password_hash = generate_password_hash(
    secrets.token_urlsafe(32),
    method="scrypt",
)

@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "auth",
        "application": "EduConecta",
    }), 200


@app.get("/ready")
def ready():
    try:
        database.list_collection_names()

    except PyMongoError:
        return jsonify({
            "status": "not_ready",
            "service": "auth",
            "database": "unavailable",
        }), 503

    return jsonify({
        "status": "ready",
        "service": "auth",
        "database": "connected",
    }), 200

@app.post("/registo")
def registar_utilizador():
    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia o pedido com Content-Type: application/json.",
        }), 415

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "error": "invalid_json",
            "message": "O corpo do pedido deve ser um objeto JSON válido.",
        }), 400

    if set(dados) - {"nome", "email", "password"}:
        return jsonify({
            "error": "unknown_fields",
            "message": "Os campos permitidos são nome, email e password.",
        }), 400

    nome = dados.get("nome")
    email = dados.get("email")
    password = dados.get("password")

    if not isinstance(nome, str) or not 2 <= len(nome.strip()) <= 150:
        return jsonify({
            "error": "invalid_name",
            "message": "O nome deve ter entre 2 e 150 caracteres.",
        }), 400

    if not isinstance(email, str) or len(email) > 254:
        return jsonify({
            "error": "invalid_email",
            "message": "Indica um email válido.",
        }), 400

    try:
        email = validate_email(
            email.strip(),
            check_deliverability=False,
        ).normalized.lower()

    except EmailNotValidError:
        return jsonify({
            "error": "invalid_email",
            "message": "Indica um email válido.",
        }), 400

    if not isinstance(password, str) or not 15 <= len(password) <= 128:
        return jsonify({
            "error": "invalid_password",
            "message": "A palavra-passe deve ter entre 15 e 128 caracteres.",
        }), 400

    utilizador = {
        "nome": nome.strip(),
        "email": email,
        "password_hash": generate_password_hash(password, method="scrypt"),
        "perfil": "encarregado",
        "estado": "pendente",
        "criado_em": datetime.now(timezone.utc),
    }

    try:
        resultado = database["utilizadores"].insert_one(utilizador)

    except DuplicateKeyError:
        return jsonify({
            "error": "email_already_registered",
            "message": "Já existe uma conta com esse email.",
        }), 409

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível criar a conta.",
        }), 503

    return jsonify({
        "id": str(resultado.inserted_id),
        "nome": utilizador["nome"],
        "email": utilizador["email"],
        "perfil": utilizador["perfil"],
        "estado": utilizador["estado"],
    }), 201

@app.post("/login")
def login():
    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia o pedido com Content-Type: application/json.",
        }), 415

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({
            "error": "invalid_json",
            "message": "O corpo do pedido deve ser um objeto JSON válido.",
        }), 400

    if set(dados) != {"email", "password"}:
        return jsonify({
            "error": "invalid_fields",
            "message": "Envia apenas os campos obrigatórios email e password.",
        }), 400

    email = dados["email"]
    password = dados["password"]

    if (
        not isinstance(email, str)
        or len(email) > 254
        or not isinstance(password, str)
        or not 1 <= len(password) <= 128
    ):
        return jsonify({
            "error": "invalid_credentials",
            "message": "Email ou palavra-passe incorretos.",
        }), 401

    try:
        email = validate_email(
            email.strip(),
            check_deliverability=False,
        ).normalized.lower()

    except EmailNotValidError:
        return jsonify({
            "error": "invalid_credentials",
            "message": "Email ou palavra-passe incorretos.",
        }), 401

    try:
        utilizador = database["utilizadores"].find_one({"email": email})

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível iniciar sessão.",
        }), 503

    password_hash = (
        utilizador.get("password_hash", dummy_password_hash)
        if utilizador
        else dummy_password_hash
    )

    password_correta = check_password_hash(password_hash, password)

    if utilizador is None or not password_correta:
        return jsonify({
            "error": "invalid_credentials",
            "message": "Email ou palavra-passe incorretos.",
        }), 401

    if utilizador.get("estado") != "ativo":
        return jsonify({
            "error": "account_inactive",
            "message": "A conta ainda não está ativa.",
        }), 403

    agora = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "sub": str(utilizador["_id"]),
            "iss": "educonecta-auth",
            "aud": "educonecta-api",
            "iat": agora,
            "exp": agora + timedelta(minutes=15),
            "jti": secrets.token_hex(16),
        },
        jwt_secret,
        algorithm="HS256",
    )

    resposta = jsonify({
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 900,
        "utilizador": {
            "id": str(utilizador["_id"]),
            "nome": utilizador["nome"],
            "email": utilizador["email"],
            "perfil": utilizador["perfil"],
        },
    })
    resposta.headers["Cache-Control"] = "no-store"

    return resposta, 200

@app.get("/me")
def consultar_conta():
    autorizacao = request.headers.get("Authorization", "")
    partes = autorizacao.split()

    if (
        len(partes) != 2
        or partes[0].lower() != "bearer"
    ):
        return jsonify({
            "error": "authentication_required",
            "message": "Envia um token no cabeçalho Authorization: Bearer.",
        }), 401, {"WWW-Authenticate": "Bearer"}

    token = partes[1]

    try:
        conteudo = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            issuer="educonecta-auth",
            audience="educonecta-api",
            options={
                "require": ["sub", "iss", "aud", "iat", "exp", "jti"],
            },
        )

    except jwt.ExpiredSignatureError:
        return jsonify({
            "error": "token_expired",
            "message": "A sessão expirou. Inicia sessão novamente.",
        }), 401, {"WWW-Authenticate": "Bearer"}

    except jwt.InvalidTokenError:
        return jsonify({
            "error": "invalid_token",
            "message": "O token é inválido.",
        }), 401, {"WWW-Authenticate": "Bearer"}

    utilizador_id = conteudo.get("sub")

    if (
        not isinstance(utilizador_id, str)
        or not ObjectId.is_valid(utilizador_id)
    ):
        return jsonify({
            "error": "invalid_token",
            "message": "O token é inválido.",
        }), 401, {"WWW-Authenticate": "Bearer"}

    try:
        utilizador = database["utilizadores"].find_one(
            {"_id": ObjectId(utilizador_id)},
            {"nome": 1, "email": 1, "perfil": 1, "estado": 1},
        )

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar a conta.",
        }), 503

    if utilizador is None:
        return jsonify({
            "error": "invalid_token",
            "message": "A conta associada à sessão já não existe.",
        }), 401, {"WWW-Authenticate": "Bearer"}

    if utilizador.get("estado") != "ativo":
        return jsonify({
            "error": "account_inactive",
            "message": "A conta não está ativa.",
        }), 403

    resposta = jsonify({
        "id": str(utilizador["_id"]),
        "nome": utilizador["nome"],
        "email": utilizador["email"],
        "perfil": utilizador["perfil"],
        "estado": utilizador["estado"],
    })
    resposta.headers["Cache-Control"] = "no-store"

    return resposta, 200