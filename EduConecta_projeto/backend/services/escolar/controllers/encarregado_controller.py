from bson import ObjectId
from flask import g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.encarregado as modelo_encarregado
from controllers.blueprint import bp
from utils.auth_client import obter_conta_para_associacao


@bp.post("/encarregados")
def criar_encarregado():
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

    if set(dados) - {"nome", "telefone"}:
        return jsonify({
            "error": "unknown_fields",
            "message": "Os campos permitidos são nome e telefone.",
        }), 400

    nome = dados.get("nome")
    telefone = dados.get("telefone", "")

    if not isinstance(nome, str) or not 2 <= len(nome.strip()) <= 150:
        return jsonify({
            "error": "invalid_name",
            "message": "O nome deve ser texto com 2 a 150 caracteres.",
        }), 400

    if not isinstance(telefone, str) or len(telefone.strip()) > 30:
        return jsonify({
            "error": "invalid_phone",
            "message": "O telefone deve ser texto com até 30 caracteres.",
        }), 400

    try:
        inserted_id, encarregado = modelo_encarregado.criar(nome.strip(), telefone.strip())

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível guardar o encarregado de educação.",
        }), 503

    return jsonify({
        "id": str(inserted_id),
        "nome": encarregado["nome"],
        "telefone": encarregado["telefone"],
    }), 201


@bp.get("/encarregados")
def listar_encarregados():
    try:
        documentos = modelo_encarregado.listar()

        encarregados = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "telefone": documento.get("telefone", ""),
            }
            for documento in documentos
        ]

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar os encarregados de educação.",
        }), 503

    return jsonify({
        "encarregados": encarregados,
        "quantidade": len(encarregados),
        "limite": 50,
    }), 200


@bp.get("/encarregados/<encarregado_id>/alunos")
def listar_alunos_encarregado(encarregado_id):
    import models.aluno as modelo_aluno

    if not ObjectId.is_valid(encarregado_id):
        return jsonify({
            "error": "invalid_guardian_id",
            "message": "O identificador do encarregado é inválido.",
        }), 400

    try:
        encarregado = modelo_encarregado.obter(encarregado_id)

        if encarregado is None:
            return jsonify({
                "error": "guardian_not_found",
                "message": "Encarregado de educação não encontrado.",
            }), 404

        documentos = modelo_aluno.listar_por_encarregado(encarregado["_id"])

        alunos = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "numero_processo": documento.get("numero_processo"),
                "turma_id": (
                    str(documento["turma_id"])
                    if documento.get("turma_id") is not None
                    else None
                ),
            }
            for documento in documentos
        ]

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar os alunos do encarregado.",
        }), 503

    return jsonify({
        "encarregado": {
            "id": str(encarregado["_id"]),
            "nome": encarregado.get("nome"),
        },
        "alunos": alunos,
        "quantidade": len(alunos),
        "limite": 50,
    }), 200


@bp.put("/encarregados/<encarregado_id>/utilizador")
def associar_conta_encarregado(encarregado_id):
    if g.utilizador.get("perfil") != "admin":
        return jsonify({
            "error": "forbidden",
            "message": "Esta operação exige uma conta de administrador.",
        }), 403

    if not ObjectId.is_valid(encarregado_id):
        return jsonify({
            "error": "invalid_guardian_id",
            "message": "O identificador do encarregado é inválido.",
        }), 400

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

    conta, erro = obter_conta_para_associacao(conta_id, request.headers.get("Authorization", ""))

    if erro is not None:
        return erro

    if conta.get("perfil") != "encarregado":
        return jsonify({
            "error": "invalid_user_profile",
            "message": "A conta deve ter o perfil encarregado.",
        }), 409

    if conta.get("estado") != "ativo":
        return jsonify({
            "error": "account_inactive",
            "message": "A conta de utilizador não está ativa.",
        }), 409

    conta_oid = ObjectId(conta_id)

    try:
        encarregado = modelo_encarregado.obter_com_utilizador(encarregado_id)

        if encarregado is None:
            return jsonify({
                "error": "guardian_not_found",
                "message": "Encarregado de educação não encontrado.",
            }), 404

        associado = modelo_encarregado.associar_utilizador(encarregado_id, conta_oid)

        if associado is None:
            return jsonify({
                "error": "guardian_already_linked",
                "message": (
                    "O encarregado já está associado a outra conta "
                    "ou o registo foi alterado entretanto."
                ),
            }), 409

    except DuplicateKeyError:
        return jsonify({
            "error": "user_already_linked",
            "message": "Esta conta já está associada a outro encarregado.",
        }), 409

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível guardar a associação.",
        }), 503

    return jsonify({
        "message": "Conta associada ao encarregado.",
        "encarregado": {
            "id": str(associado["_id"]),
            "nome": associado.get("nome"),
            "utilizador_id": str(associado["utilizador_id"]),
        },
    }), 200
