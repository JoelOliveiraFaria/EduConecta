"""Controller: rotas de gestão de profissionais (docentes, educadoras, auxiliares)."""

from bson import ObjectId
from flask import jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.profissional as modelo_profissional
from controllers.blueprint import bp
from utils.auth_client import criar_conta_utilizador
from utils.validacao import (
    validar_cc,
    validar_data_iso,
    validar_email_superficial,
    validar_morada,
    validar_telemovel,
)

PERFIS_PROFISSIONAL = {"docente", "educadora", "auxiliar"}


@bp.post("/profissionais")
def criar_profissional():
    """Cria o registo de profissional E a sua conta de login, num único
    pedido: o auth cria a conta (perfil docente/educadora/auxiliar, conforme
    indicado) e envia uma password temporária para o email indicado — mesmo
    fluxo já usado em POST /encarregados. Não é preciso nenhuma conta
    criada à parte."""
    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia Content-Type: application/json.",
        }), 415

    dados = request.get_json(silent=True)

    campos_permitidos = {"nome", "email", "cc", "telemovel", "perfil", "morada", "data_admissao"}
    obrigatorios = {"nome", "email", "cc", "perfil"}

    if (
        not isinstance(dados, dict)
        or set(dados) - campos_permitidos
        or obrigatorios - set(dados)
    ):
        return jsonify({
            "error": "invalid_fields",
            "message": (
                "Os campos nome, email, cc e perfil são obrigatórios; "
                "telemovel, morada e data_admissao são opcionais. Não são permitidos outros campos."
            ),
        }), 400

    nome = dados.get("nome")
    email = dados.get("email")
    cc = dados.get("cc")
    telemovel = dados.get("telemovel", "")
    perfil = dados.get("perfil")
    morada = dados.get("morada", "")
    data_admissao = dados.get("data_admissao")

    if not isinstance(nome, str) or not 2 <= len(nome.strip()) <= 150:
        return jsonify({
            "error": "invalid_name",
            "message": "O nome deve ser texto com 2 a 150 caracteres.",
        }), 400

    if not validar_cc(cc):
        return jsonify({
            "error": "invalid_cc",
            "message": "O número de cartão de cidadão deve ser texto com 5 a 30 caracteres.",
        }), 400

    if not validar_telemovel(telemovel):
        return jsonify({
            "error": "invalid_phone",
            "message": "O telemóvel deve ser texto com até 30 caracteres.",
        }), 400

    if not validar_email_superficial(email):
        return jsonify({
            "error": "invalid_email",
            "message": "Indica um email válido.",
        }), 400

    if not isinstance(perfil, str) or perfil not in PERFIS_PROFISSIONAL:
        return jsonify({
            "error": "invalid_profile",
            "message": "O perfil deve ser docente, educadora ou auxiliar.",
        }), 400

    if not validar_morada(morada):
        return jsonify({
            "error": "invalid_address",
            "message": "A morada deve ser texto com até 200 caracteres.",
        }), 400

    if data_admissao is not None and validar_data_iso(data_admissao) is None:
        return jsonify({
            "error": "invalid_admission_date",
            "message": "A data de admissão deve ter o formato AAAA-MM-DD.",
        }), 400

    conta, erro = criar_conta_utilizador(
        nome.strip(), email.strip(), perfil, request.headers.get("Authorization", "")
    )

    if erro is not None:
        return erro

    try:
        inserted_id, profissional = modelo_profissional.criar(
            ObjectId(conta["id"]),
            nome.strip(),
            perfil,
            cc.strip(),
            telemovel.strip(),
            morada.strip(),
            data_admissao,
        )

    except DuplicateKeyError:
        return jsonify({
            "error": "professional_already_registered",
            "message": "Esta conta já tem um registo profissional.",
        }), 409

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": (
                "A conta de login foi criada e o email foi enviado, mas não foi "
                "possível guardar o registo profissional. Contacta a "
                "administração — a conta já existe, não a voltes a criar."
            ),
            "utilizador_id": conta["id"],
        }), 503

    return jsonify({
        "id": str(inserted_id),
        "utilizador_id": str(profissional["utilizador_id"]),
        "nome": profissional["nome"],
        "perfil": profissional["perfil"],
        "cc": profissional["cc"],
        "telemovel": profissional["telemovel"],
        "morada": profissional["morada"],
        "data_admissao": profissional["data_admissao"],
        "email": conta.get("email"),
        "estado": conta.get("estado"),
        "deve_alterar_password": conta.get("deve_alterar_password"),
    }), 201


@bp.get("/profissionais")
def listar_profissionais():
    """Lista até 50 profissionais."""
    try:
        documentos = modelo_profissional.listar()

        profissionais = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "perfil": documento.get("perfil"),
                "cc": documento.get("cc", ""),
                "telemovel": documento.get("telemovel", ""),
                "morada": documento.get("morada", ""),
                "data_admissao": documento.get("data_admissao"),
                "utilizador_id": (
                    str(documento["utilizador_id"])
                    if documento.get("utilizador_id") is not None
                    else None
                ),
            }
            for documento in documentos
        ]

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar os profissionais.",
        }), 503

    return jsonify({
        "profissionais": profissionais,
        "quantidade": len(profissionais),
        "limite": 50,
    }), 200
