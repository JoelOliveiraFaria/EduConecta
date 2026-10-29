"""Controller: rotas de gestão de encarregados de educação e ligação a contas de utilizador."""

from bson import ObjectId
from flask import g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.encarregado as modelo_encarregado
from controllers.blueprint import bp
from utils.auth_client import criar_conta_utilizador, obter_conta_para_associacao
from utils.validacao import validar_cc, validar_email_superficial, validar_telemovel


@bp.post("/encarregados")
def criar_encarregado():
    """Cria um encarregado de educação E a sua conta de login, num único
    pedido: o auth cria a conta (perfil "encarregado") e envia uma password
    temporária para o email indicado — tal como já acontece para docentes/
    educadoras/auxiliares em POST /admin/utilizadores. Não é preciso nenhum
    passo manual a seguir (PUT .../utilizador continua a existir, mas é só
    para ligar uma conta já existente a um encarregado, não é o caminho
    normal)."""
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

    campos_permitidos = {"nome", "email", "cc", "telemovel"}
    obrigatorios = {"nome", "email", "cc"}

    if set(dados) - campos_permitidos or obrigatorios - set(dados):
        return jsonify({
            "error": "invalid_fields",
            "message": (
                "Os campos nome, email e cc são obrigatórios; "
                "telemovel é opcional. Não são permitidos outros campos."
            ),
        }), 400

    nome = dados.get("nome")
    email = dados.get("email")
    cc = dados.get("cc")
    telemovel = dados.get("telemovel", "")

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

    conta, erro = criar_conta_utilizador(
        nome.strip(), email.strip(), "encarregado", request.headers.get("Authorization", "")
    )

    if erro is not None:
        return erro

    try:
        inserted_id, encarregado = modelo_encarregado.criar(
            nome.strip(), cc.strip(), telemovel.strip(), ObjectId(conta["id"])
        )

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": (
                "A conta de login foi criada e o email foi enviado, mas não foi "
                "possível guardar o registo escolar do encarregado. Contacta a "
                "administração — a conta já existe, não a voltes a criar."
            ),
            "utilizador_id": conta["id"],
        }), 503

    return jsonify({
        "id": str(inserted_id),
        "nome": encarregado["nome"],
        "cc": encarregado["cc"],
        "telemovel": encarregado["telemovel"],
        "utilizador_id": str(encarregado["utilizador_id"]),
        "email": conta.get("email"),
        "estado": conta.get("estado"),
        "deve_alterar_password": conta.get("deve_alterar_password"),
    }), 201


@bp.get("/encarregados")
def listar_encarregados():
    """Lista até 50 encarregados de educação."""
    try:
        documentos = modelo_encarregado.listar()

        encarregados = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "cc": documento.get("cc", ""),
                "telemovel": documento.get("telemovel", ""),
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
    """Lista os educandos de um encarregado (visão de admin, por id)."""
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
    """Liga uma conta de utilizador (perfil 'encarregado', já criada no auth) a este
    registo de encarregado.

    Nota: esta rota já não está em PERMISSOES_PESSOAIS, por isso o
    before_request (verificar_acesso_escolar) já só deixa passar admins —
    esta verificação de perfil aqui dentro é redundante com essa, mas foi
    mantida como está no código original (comportamento preservado tal e
    qual durante o refactor para MVC, não foi limpa de propósito)."""
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
