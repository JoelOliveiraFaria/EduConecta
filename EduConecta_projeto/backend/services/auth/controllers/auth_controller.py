import secrets

import aiosmtplib
from bson import ObjectId
from email_validator import EmailNotValidError, validate_email
from pymongo.errors import DuplicateKeyError, PyMongoError
from quart import Blueprint, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

import models.utilizador as modelo_utilizador
from utils import email as email_utils
from utils.tokens import descodificar_token, gerar_token

bp = Blueprint("auth", __name__)

dummy_password_hash = generate_password_hash(
    secrets.token_urlsafe(32),
    method="scrypt",
)

PERFIS_PERMITIDOS = {"admin", "encarregado", "docente", "educadora", "auxiliar"}


@bp.before_request
async def bloquear_registo_publico():
    if request.endpoint == "auth.registar_utilizador":
        return jsonify({
            "error": "registration_disabled",
            "message": "A criação de contas é feita pela administração.",
        }), 403


@bp.after_request
async def impedir_cache_autenticacao(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@bp.post("/registo")
async def registar_utilizador():
    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia o pedido com Content-Type: application/json.",
        }), 415

    dados = await request.get_json(silent=True)

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
        email = validate_email(email.strip(), check_deliverability=False).normalized.lower()

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

    try:
        inserted_id, utilizador = await modelo_utilizador.criar_encarregado(
            nome.strip(), email, password
        )

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
        "id": str(inserted_id),
        "nome": utilizador["nome"],
        "email": utilizador["email"],
        "perfil": utilizador["perfil"],
        "estado": utilizador["estado"],
    }), 201


@bp.post("/login")
async def login():
    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia o pedido com Content-Type: application/json.",
        }), 415

    dados = await request.get_json(silent=True)

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
        email = validate_email(email.strip(), check_deliverability=False).normalized.lower()

    except EmailNotValidError:
        return jsonify({
            "error": "invalid_credentials",
            "message": "Email ou palavra-passe incorretos.",
        }), 401

    try:
        utilizador = await modelo_utilizador.obter_por_email(email)

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível iniciar sessão.",
        }), 503

    password_hash = (
        utilizador.get("password_hash", dummy_password_hash) if utilizador else dummy_password_hash
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

    token = gerar_token(utilizador["_id"])

    resposta = jsonify({
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": 900,
        "deve_alterar_password": bool(utilizador.get("deve_alterar_password", False)),
        "utilizador": {
            "id": str(utilizador["_id"]),
            "nome": utilizador["nome"],
            "email": utilizador["email"],
            "perfil": utilizador["perfil"],
        },
    })

    return resposta, 200


@bp.get("/me")
async def consultar_conta():
    utilizador_id, erro = descodificar_token(request.headers.get("Authorization", ""))

    if erro is not None:
        return erro

    try:
        utilizador = await modelo_utilizador.obter_por_id(
            utilizador_id,
            {"nome": 1, "email": 1, "perfil": 1, "estado": 1, "deve_alterar_password": 1},
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

    return jsonify({
        "id": str(utilizador["_id"]),
        "nome": utilizador["nome"],
        "email": utilizador["email"],
        "perfil": utilizador["perfil"],
        "estado": utilizador["estado"],
    }), 200


@bp.post("/password/alterar")
async def alterar_password():
    utilizador_id, erro = descodificar_token(request.headers.get("Authorization", ""))

    if erro is not None:
        return erro

    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia o pedido com Content-Type: application/json.",
        }), 415

    dados = await request.get_json(silent=True)

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
        utilizador = await modelo_utilizador.obter_por_id(
            utilizador_id, {"password_hash": 1, "estado": 1}
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

        await modelo_utilizador.atualizar_password(utilizador["_id"], password_nova)

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível alterar a palavra-passe.",
        }), 503

    return jsonify({"message": "Palavra-passe alterada com sucesso."}), 200


@bp.post("/admin/utilizadores")
async def criar_utilizador_com_email():
    utilizador_id, erro = descodificar_token(request.headers.get("Authorization", ""))

    if erro is not None:
        return erro

    try:
        administrador = await modelo_utilizador.obter_por_id(
            utilizador_id, {"perfil": 1, "estado": 1, "deve_alterar_password": 1}
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

    dados = await request.get_json(silent=True)

    if not isinstance(dados, dict) or set(dados) != {"nome", "email", "perfil"}:
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
        email = validate_email(email.strip(), check_deliverability=False).normalized.lower()

    except EmailNotValidError:
        return jsonify({
            "error": "invalid_email",
            "message": "Indica um email válido.",
        }), 400

    if not isinstance(perfil, str) or perfil not in PERFIS_PERMITIDOS:
        return jsonify({
            "error": "invalid_profile",
            "message": "Os perfis disponíveis são admin, encarregado, docente, educadora e auxiliar.",
        }), 400

    if not email_utils.smtp_configurado():
        return jsonify({
            "error": "email_not_configured",
            "message": "O envio de emails não está configurado.",
        }), 503

    temporaria = secrets.token_urlsafe(24)

    try:
        existente = await modelo_utilizador.existe_email(email)

        if existente is not None:
            return jsonify({
                "error": "email_already_registered",
                "message": "Já existe uma conta com esse email.",
            }), 409

        conta_id, utilizador = await modelo_utilizador.criar_com_password_temporaria(
            nome.strip(), email, perfil, temporaria, utilizador_id
        )

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

    try:
        await email_utils.enviar_credenciais(nome.strip(), email, temporaria)

    except (aiosmtplib.SMTPException, OSError):
        return jsonify({
            "error": "email_delivery_uncertain",
            "message": (
                "Não foi possível confirmar o envio. "
                "A conta permanece bloqueada para revisão administrativa."
            ),
            "id": str(conta_id),
        }), 503

    try:
        resultado = await modelo_utilizador.marcar_email_credenciais_enviado(conta_id)

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


@bp.get("/admin/utilizadores/<conta_id>")
async def consultar_utilizador_administracao(conta_id):
    administrador_id, erro = descodificar_token(request.headers.get("Authorization", ""))

    if erro is not None:
        return erro

    if not ObjectId.is_valid(conta_id):
        return jsonify({
            "error": "invalid_user_id",
            "message": "O identificador da conta é inválido.",
        }), 400

    try:
        administrador = await modelo_utilizador.obter_por_id(
            administrador_id, {"perfil": 1, "estado": 1, "deve_alterar_password": 1}
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

        utilizador = await modelo_utilizador.obter_por_id(
            conta_id, {"nome": 1, "email": 1, "perfil": 1, "estado": 1}
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
