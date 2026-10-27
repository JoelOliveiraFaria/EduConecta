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


def _descodificar_token(autorizacao):
    partes = autorizacao.split()

    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None, (
            jsonify({
                "error": "authentication_required",
                "message": "Envia um token no cabeçalho Authorization: Bearer.",
            }),
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    try:
        conteudo = jwt.decode(
            partes[1],
            jwt_secret,
            algorithms=["HS256"],
            issuer="educonecta-auth",
            audience="educonecta-api",
            options={
                "require": ["sub", "iss", "aud", "iat", "exp", "jti"],
            },
        )

    except jwt.ExpiredSignatureError:
        return None, (
            jsonify({
                "error": "token_expired",
                "message": "A sessão expirou. Inicia sessão novamente.",
            }),
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    except jwt.InvalidTokenError:
        return None, (
            jsonify({
                "error": "invalid_token",
                "message": "O token é inválido.",
            }),
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    utilizador_id = conteudo.get("sub")

    if not isinstance(utilizador_id, str) or not ObjectId.is_valid(utilizador_id):
        return None, (
            jsonify({
                "error": "invalid_token",
                "message": "O token é inválido.",
            }),
            401,
            {"WWW-Authenticate": "Bearer"},
        )

    return utilizador_id, None


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
    utilizador_id, erro = _descodificar_token(request.headers.get("Authorization", ""))

    if erro is not None:
        return erro

    try:
        utilizador = database["utilizadores"].find_one(
            {"_id": ObjectId(utilizador_id)},
            {
                "nome": 1,
                "email": 1,
                "perfil": 1,
                "estado": 1,
                "deve_alterar_password": 1,
            },
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


    if utilizador.get("deve_alterar_password"):
        return jsonify({
            "error": "password_change_required",
            "message": "Tens de definir uma nova palavra-passe antes de continuar.",
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


@app.post("/password/alterar")
def alterar_password():
    utilizador_id, erro = _descodificar_token(request.headers.get("Authorization", ""))

    if erro is not None:
        return erro

    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia o pedido com Content-Type: application/json.",
        }), 415


    dados = request.get_json(silent=True)


    if (
        not isinstance(dados, dict)
        or set(dados) != {"password_atual", "password_nova"}
        or not isinstance(dados["password_atual"], str)
        or not isinstance(dados["password_nova"], str)
    ):
        return jsonify({
            "error": "invalid_fields",
            "message": "Envia apenas password_atual e password_nova.",
        }), 400


    password_atual = dados["password_atual"]
    password_nova = dados["password_nova"]


    if not 1 <= len(password_atual) <= 128:
        return jsonify({
            "error": "invalid_credentials",
            "message": "Palavra-passe atual incorreta.",
        }), 401


    if not 15 <= len(password_nova) <= 128 or password_nova == password_atual:
        return jsonify({
            "error": "invalid_password",
            "message": "A nova palavra-passe deve ter entre 15 e 128 caracteres e ser diferente da atual.",
        }), 400


    try:
        utilizador = database["utilizadores"].find_one(
            {"_id": ObjectId(utilizador_id)},
            {"password_hash": 1, "estado": 1},
        )


        if utilizador is None or utilizador.get("estado") != "ativo":
            return jsonify({
                "error": "invalid_token",
                "message": "A conta associada à sessão já não está disponível.",
            }), 401, {"WWW-Authenticate": "Bearer"}


        if not check_password_hash(utilizador["password_hash"], password_atual):
            return jsonify({
                "error": "invalid_credentials",
                "message": "Palavra-passe atual incorreta.",
            }), 401


        database["utilizadores"].update_one(
            {"_id": utilizador["_id"]},
            {
                "$set": {
                    "password_hash": generate_password_hash(password_nova, method="scrypt"),
                    "deve_alterar_password": False,
                    "password_alterada_em": datetime.now(timezone.utc),
                },
                "$unset": {"password_temporaria_expira_em": ""},
            },
        )


    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível alterar a palavra-passe.",
        }), 503


    resposta = jsonify({
        "message": "Palavra-passe alterada com sucesso.",
    })
    resposta.headers["Cache-Control"] = "no-store"


    return resposta, 200

import smtplib
import ssl

from email.message import EmailMessage
from email.utils import formatdate, make_msgid


@app.before_request
def bloquear_registo_publico():
    if request.endpoint == "registar_utilizador":
        return jsonify({
            "error": "registration_disabled",
            "message": "A criação de contas é feita pela administração.",
        }), 403


@app.post("/admin/utilizadores")
def criar_utilizador_com_email():
    utilizador_id, erro = _descodificar_token(
        request.headers.get("Authorization", "")
    )

    if erro is not None:
        return erro

    try:
        administrador = database["utilizadores"].find_one(
            {"_id": ObjectId(utilizador_id)},
            {
                "perfil": 1,
                "estado": 1,
                "deve_alterar_password": 1,
            },
        )
    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível verificar a conta.",
        }), 503

    if (
        administrador is None
        or administrador.get("estado") != "ativo"
        or administrador.get("perfil") != "admin"
        or administrador.get("deve_alterar_password")
    ):
        return jsonify({
            "error": "forbidden",
            "message": "Esta operação exige uma conta de administrador autorizada.",
        }), 403

    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia Content-Type: application/json.",
        }), 415

    dados = request.get_json(silent=True)

    if (
        not isinstance(dados, dict)
        or set(dados) != {"nome", "email", "perfil"}
    ):
        return jsonify({
            "error": "invalid_fields",
            "message": "Envia apenas nome, email e perfil.",
        }), 400

    nome = dados["nome"]
    email = dados["email"]
    perfil = dados["perfil"]

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

        perfis_permitidos = {
        "admin",
        "encarregado",
        "docente",
        "educadora",
        "auxiliar",
    }

    if not isinstance(perfil, str) or perfil not in {
        "admin",
        "encarregado",
        "docente",
        "educadora",
        "auxiliar",
    }:
        return jsonify({
            "error": "invalid_profile",
            "message": (
                "Os perfis disponíveis são admin, encarregado, "
                "docente, educadora e auxiliar."
            ),
        }), 400
    
    remetente = os.environ.get("SMTP_USERNAME")
    password_smtp = os.environ.get("SMTP_PASSWORD")

    if not remetente or not password_smtp:
        return jsonify({
            "error": "email_not_configured",
            "message": "O envio de emails não está configurado.",
        }), 503

    temporaria = secrets.token_urlsafe(24)

    utilizador = {
        "nome": nome.strip(),
        "email": email,
        "perfil": perfil,
        "estado": "provisionamento",
        "password_hash": generate_password_hash(
            temporaria,
            method="scrypt",
        ),
        "deve_alterar_password": True,
        "criado_em": datetime.now(timezone.utc),
        "criado_por": ObjectId(utilizador_id),
        "email_credenciais_estado": "pendente",
    }

    try:
        existente = database["utilizadores"].find_one(
            {"email": email},
            {"_id": 1},
        )

        if existente is not None:
            return jsonify({
                "error": "email_already_registered",
                "message": "Já existe uma conta com esse email.",
            }), 409

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

    conta_id = resultado.inserted_id

    mensagem = EmailMessage()
    mensagem["From"] = remetente
    mensagem["To"] = email
    mensagem["Subject"] = "EduConecta - Credenciais de primeiro acesso"
    mensagem["Date"] = formatdate(localtime=False)
    mensagem["Message-ID"] = make_msgid()

    mensagem.set_content(
        f"Olá, {nome.strip()}!\n\n"
        "Foi criada uma conta para ti na EduConecta.\n\n"
        f"Email de acesso: {email}\n"
        f"Palavra-passe temporária: {temporaria}\n\n"
        "No primeiro acesso, terás de definir uma nova palavra-passe "
        "antes de utilizar as funcionalidades da aplicação.\n\n"
        "Não partilhes estas credenciais.\n"
        "Se não reconheces esta conta, contacta a administração.\n\n"
        "Equipa EduConecta\n"
    )

    try:
        with smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            context=ssl.create_default_context(),
            timeout=15,
        ) as servidor:
            servidor.login(remetente, password_smtp)
            recusados = servidor.send_message(mensagem)

            if recusados:
                raise smtplib.SMTPException(
                    "O destinatário foi recusado."
                )

    except (smtplib.SMTPException, OSError):
        return jsonify({
            "error": "email_delivery_uncertain",
            "message": (
                "Não foi possível confirmar o envio. "
                "A conta permanece bloqueada para revisão administrativa."
            ),
            "id": str(conta_id),
        }), 503

    try:
        resultado = database["utilizadores"].update_one(
            {
                "_id": conta_id,
                "estado": "provisionamento",
            },
            {
                "$set": {
                    "estado": "ativo",
                    "email_credenciais_estado": "aceite_pelo_smtp",
                    "email_credenciais_enviado_em": datetime.now(timezone.utc),
                },
            },
        )

        if resultado.matched_count != 1:
            return jsonify({
                "error": "activation_failed",
                "message": (
                    "O email foi aceite pelo servidor, mas a conta "
                    "não pôde ser ativada. Contacta a administração."
                ),
                "id": str(conta_id),
            }), 503

    except PyMongoError:
        return jsonify({
            "error": "activation_failed",
            "message": (
                "O email foi aceite pelo servidor, mas não foi possível "
                "confirmar a ativação da conta."
            ),
            "id": str(conta_id),
        }), 503

    return jsonify({
        "id": str(conta_id),
        "nome": utilizador["nome"],
        "email": email,
        "perfil": perfil,
        "estado": "ativo",
        "deve_alterar_password": True,
        "email_credenciais_estado": "aceite_pelo_smtp",
    }), 201


@app.after_request
def impedir_cache_autenticacao(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    return resposta

@app.get("/admin/utilizadores/<conta_id>")
def consultar_utilizador_administracao(conta_id):
    administrador_id, erro = _descodificar_token(
        request.headers.get("Authorization", "")
    )

    if erro is not None:
        return erro

    if not ObjectId.is_valid(conta_id):
        return jsonify({
            "error": "invalid_user_id",
            "message": "O identificador da conta é inválido.",
        }), 400

    try:
        administrador = database["utilizadores"].find_one(
            {"_id": ObjectId(administrador_id)},
            {
                "perfil": 1,
                "estado": 1,
                "deve_alterar_password": 1,
            },
        )

        if (
            administrador is None
            or administrador.get("perfil") != "admin"
            or administrador.get("estado") != "ativo"
            or administrador.get("deve_alterar_password")
        ):
            return jsonify({
                "error": "forbidden",
                "message": "Esta operação exige uma conta de administrador autorizada.",
            }), 403

        utilizador = database["utilizadores"].find_one(
            {"_id": ObjectId(conta_id)},
            {
                "nome": 1,
                "email": 1,
                "perfil": 1,
                "estado": 1,
            },
        )

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar a conta.",
        }), 503

    if utilizador is None:
        return jsonify({
            "error": "user_not_found",
            "message": "Conta de utilizador não encontrada.",
        }), 404

    return jsonify({
        "id": str(utilizador["_id"]),
        "nome": utilizador.get("nome"),
        "email": utilizador.get("email"),
        "perfil": utilizador.get("perfil"),
        "estado": utilizador.get("estado"),
    }), 200