from bson import ObjectId
from flask import jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.profissional as modelo_profissional
from controllers.blueprint import bp
from utils.auth_client import consultar_conta_profissional_auth


@bp.post("/profissionais")
def criar_profissional():
    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia Content-Type: application/json.",
        }), 415

    dados = request.get_json(silent=True)

    if (
        not isinstance(dados, dict)
        or set(dados) != {"utilizador_id"}
        or not isinstance(dados["utilizador_id"], str)
        or not ObjectId.is_valid(dados["utilizador_id"])
    ):
        return jsonify({
            "error": "invalid_fields",
            "message": "Envia apenas utilizador_id com um identificador válido.",
        }), 400

    conta_id = str(ObjectId(dados["utilizador_id"]))
    conta, erro = consultar_conta_profissional_auth(
        conta_id, request.headers.get("Authorization", "")
    )

    if erro is not None:
        return erro

    if conta.get("perfil") not in {"docente", "educadora", "auxiliar"}:
        return jsonify({
            "error": "invalid_user_profile",
            "message": "A conta deve ter perfil docente, educadora ou auxiliar.",
        }), 409

    if conta.get("estado") != "ativo":
        return jsonify({
            "error": "account_inactive",
            "message": "A conta de utilizador não está ativa.",
        }), 409

    try:
        if modelo_profissional.existe_por_utilizador(ObjectId(conta_id)) is not None:
            return jsonify({
                "error": "professional_already_registered",
                "message": "Esta conta já tem um registo profissional.",
            }), 409

        inserted_id, profissional = modelo_profissional.criar(
            ObjectId(conta_id), conta.get("nome"), conta["perfil"]
        )

    except DuplicateKeyError:
        return jsonify({
            "error": "professional_already_registered",
            "message": "Esta conta já tem um registo profissional.",
        }), 409

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível criar o profissional.",
        }), 503

    return jsonify({
        "id": str(inserted_id),
        "utilizador_id": conta_id,
        "nome": profissional["nome"],
        "perfil": profissional["perfil"],
    }), 201


@bp.get("/profissionais")
def listar_profissionais():
    try:
        documentos = modelo_profissional.listar()

        profissionais = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "perfil": documento.get("perfil"),
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
