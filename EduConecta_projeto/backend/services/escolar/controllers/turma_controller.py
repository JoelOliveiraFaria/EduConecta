"""Controller: rotas de gestão de turmas e das suas associações a alunos/profissionais.

As rotas "/me/turmas..." (de um profissional sobre as suas próprias turmas)
estão listadas em PERMISSOES_PESSOAIS; as restantes exigem admin.
"""

from bson import ObjectId
from flask import g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.profissional as modelo_profissional
import models.turma as modelo_turma
from controllers.blueprint import bp, obter_profissional_da_sessao
from utils.auth_client import consultar_conta_profissional_auth


@bp.post("/turmas")
def criar_turma():
    """Cria uma turma. ano_letivo tem de ser "AAAA/AAAA" com dois anos consecutivos."""
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

    campos_permitidos = {"nome", "ano_letivo", "tipo", "capacidade"}

    if set(dados) - campos_permitidos or "tipo" not in dados:
        return jsonify({
            "error": "unknown_fields",
            "message": (
                "Os campos permitidos são nome, ano_letivo e tipo (obrigatórios) "
                "e capacidade (opcional)."
            ),
        }), 400

    nome = dados.get("nome")
    ano_letivo = dados.get("ano_letivo")
    tipo = dados.get("tipo")
    capacidade = dados.get("capacidade")

    if not isinstance(tipo, str) or tipo not in modelo_turma.TIPOS:
        return jsonify({
            "error": "invalid_class_type",
            "message": "O tipo deve ser creche ou basico.",
        }), 400

    if not isinstance(nome, str) or not 1 <= len(nome.strip()) <= 100:
        return jsonify({
            "error": "invalid_class_name",
            "message": "O nome da turma deve ter entre 1 e 100 caracteres.",
        }), 400

    if not isinstance(ano_letivo, str):
        return jsonify({
            "error": "invalid_school_year",
            "message": "O ano letivo deve ter o formato AAAA/AAAA.",
        }), 400

    ano_letivo = ano_letivo.strip()
    partes = ano_letivo.split("/")

    if (
        len(partes) != 2
        or any(
            len(parte) != 4 or not parte.isascii() or not parte.isdigit()
            for parte in partes
        )
    ):
        return jsonify({
            "error": "invalid_school_year",
            "message": "O ano letivo deve ter o formato AAAA/AAAA.",
        }), 400

    primeiro_ano, segundo_ano = map(int, partes)

    if not 1900 <= primeiro_ano <= 9998 or segundo_ano != primeiro_ano + 1:
        return jsonify({
            "error": "invalid_school_year",
            "message": "O ano letivo deve conter dois anos consecutivos.",
        }), 400

    if capacidade is not None and (
        not isinstance(capacidade, int) or isinstance(capacidade, bool) or not 1 <= capacidade <= 1000
    ):
        return jsonify({
            "error": "invalid_capacity",
            "message": "A capacidade deve ser um número inteiro entre 1 e 1000.",
        }), 400

    try:
        inserted_id, turma = modelo_turma.criar(nome.strip(), ano_letivo, tipo, capacidade)

    except DuplicateKeyError:
        return jsonify({
            "error": "duplicate_class",
            "message": "Já existe uma turma com esse nome nesse ano letivo.",
        }), 409

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível guardar a turma.",
        }), 503

    return jsonify({
        "id": str(inserted_id),
        "nome": turma["nome"],
        "ano_letivo": turma["ano_letivo"],
        "tipo": turma["tipo"],
        "capacidade": turma["capacidade"],
    }), 201


@bp.get("/turmas")
def listar_turmas():
    """Lista até 50 turmas."""
    try:
        documentos = modelo_turma.listar()

        turmas = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "ano_letivo": documento.get("ano_letivo"),
                "tipo": documento.get("tipo"),
                "capacidade": documento.get("capacidade"),
            }
            for documento in documentos
        ]

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar as turmas.",
        }), 503

    return jsonify({
        "turmas": turmas,
        "quantidade": len(turmas),
        "limite": 50,
    }), 200


@bp.get("/turmas/<turma_id>")
def obter_turma(turma_id):
    """Detalhe de uma turma: profissionais atribuídos.

    Admin pode consultar qualquer turma; um profissional só consegue ver
    turmas onde está atribuído (RNF01) — para as restantes, devolve 404,
    não 403, para não revelar que a turma existe a quem não tem acesso.
    Não há distinção entre os profissionais atribuídos (ex: "diretor de
    turma") — qualquer um pode fazer tudo o que a turma permite a um
    profissional, incluindo decidir justificações de faltas no assiduidade.
    """
    if not ObjectId.is_valid(turma_id):
        return jsonify({
            "error": "invalid_class_id",
            "message": "O identificador da turma é inválido.",
        }), 400

    try:
        turma = modelo_turma.obter_detalhe(turma_id)

        if turma is None:
            return jsonify({
                "error": "class_not_found",
                "message": "Turma não encontrada.",
            }), 404

        profissionais_ids = turma.get("profissionais_ids", [])

        if g.utilizador["perfil"] != "admin":
            profissional, erro = obter_profissional_da_sessao()

            if erro is not None:
                return erro

            if profissional["_id"] not in profissionais_ids:
                return jsonify({
                    "error": "class_not_found",
                    "message": "Turma não encontrada.",
                }), 404

        profissionais_docs = modelo_profissional.listar_por_ids(profissionais_ids)

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar a turma.",
        }), 503

    return jsonify({
        "id": str(turma["_id"]),
        "nome": turma.get("nome"),
        "ano_letivo": turma.get("ano_letivo"),
        "tipo": turma.get("tipo"),
        "capacidade": turma.get("capacidade"),
        "profissionais": [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "perfil": documento.get("perfil"),
            }
            for documento in profissionais_docs
        ],
    }), 200


@bp.get("/turmas/<turma_id>/alunos")
def listar_alunos_turma(turma_id):
    """Lista os alunos de uma turma (visão de admin, qualquer turma)."""
    import models.aluno as modelo_aluno

    if not ObjectId.is_valid(turma_id):
        return jsonify({
            "error": "invalid_class_id",
            "message": "O identificador da turma é inválido.",
        }), 400

    try:
        turma = modelo_turma.obter(turma_id)

        if turma is None:
            return jsonify({
                "error": "class_not_found",
                "message": "Turma não encontrada.",
            }), 404

        documentos = modelo_aluno.listar_por_turma(turma["_id"])

        alunos = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "numero_processo": documento.get("numero_processo"),
            }
            for documento in documentos
        ]

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar os alunos da turma.",
        }), 503

    return jsonify({
        "turma": {
            "id": str(turma["_id"]),
            "nome": turma.get("nome"),
            "ano_letivo": turma.get("ano_letivo"),
            "tipo": turma.get("tipo"),
            "capacidade": turma.get("capacidade"),
        },
        "alunos": alunos,
        "quantidade": len(alunos),
        "limite": 50,
    }), 200


@bp.put("/turmas/<turma_id>/profissionais/<profissional_id>")
def associar_profissional_turma(turma_id, profissional_id):
    """Atribui um profissional a uma turma.

    Antes de gravar, confirma junto do auth que a conta ligada ao
    profissional está ativa e que o perfil da conta ainda bate certo com o
    perfil guardado no registo profissional (a conta pode ter mudado de
    perfil no auth depois do registo ter sido criado aqui). Uma turma só
    pode ter um docente (o "professor" é sempre o responsável principal da
    turma) — educadoras e auxiliares não têm esse limite.
    """
    if not ObjectId.is_valid(turma_id):
        return jsonify({
            "error": "invalid_class_id",
            "message": "O identificador da turma é inválido.",
        }), 400

    if not ObjectId.is_valid(profissional_id):
        return jsonify({
            "error": "invalid_professional_id",
            "message": "O identificador do profissional é inválido.",
        }), 400

    try:
        profissional = modelo_profissional.obter(profissional_id)

        if profissional is None:
            return jsonify({
                "error": "professional_not_found",
                "message": "Profissional não encontrado.",
            }), 404

        conta_oid = profissional.get("utilizador_id")

        if not isinstance(conta_oid, ObjectId):
            return jsonify({
                "error": "professional_account_not_linked",
                "message": "O profissional não tem uma conta válida associada.",
            }), 409

        conta, erro = consultar_conta_profissional_auth(
            str(conta_oid), request.headers.get("Authorization", "")
        )

        if erro is not None:
            return erro

        if (
            conta.get("estado") != "ativo"
            or conta.get("perfil") not in {"docente", "educadora", "auxiliar"}
            or conta.get("perfil") != profissional.get("perfil")
        ):
            return jsonify({
                "error": "professional_account_invalid",
                "message": "A conta não está ativa ou o perfil não corresponde.",
            }), 409

        if profissional.get("perfil") == "docente":
            ids_atuais = modelo_turma.profissionais_atribuidos(turma_id)

            if ids_atuais is None:
                return jsonify({
                    "error": "class_not_found",
                    "message": "Turma não encontrada.",
                }), 404

            colegas = modelo_profissional.listar_por_ids(ids_atuais)

            if any(
                colega["perfil"] == "docente" and colega["_id"] != profissional["_id"]
                for colega in colegas
            ):
                return jsonify({
                    "error": "class_already_has_teacher",
                    "message": "Esta turma já tem um docente atribuído — só pode ter um.",
                }), 409

        turma = modelo_turma.adicionar_profissional(turma_id, profissional["_id"])

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível associar o profissional à turma.",
        }), 503

    if turma is None:
        return jsonify({
            "error": "class_not_found",
            "message": "Turma não encontrada.",
        }), 404

    return jsonify({
        "message": "Profissional associado à turma.",
        "turma": {
            "id": str(turma["_id"]),
            "nome": turma.get("nome"),
            "ano_letivo": turma.get("ano_letivo"),
            "tipo": turma.get("tipo"),
            "capacidade": turma.get("capacidade"),
        },
        "profissional": {
            "id": str(profissional["_id"]),
            "nome": conta.get("nome"),
            "perfil": conta["perfil"],
        },
    }), 200


@bp.get("/me/turmas")
def listar_minhas_turmas():
    """Lista as turmas atribuídas ao profissional autenticado (rota pessoal)."""
    profissional, erro = obter_profissional_da_sessao()

    if erro is not None:
        return erro

    try:
        documentos = modelo_turma.listar_por_profissional(profissional["_id"])

        turmas = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "ano_letivo": documento.get("ano_letivo"),
                "tipo": documento.get("tipo"),
                "capacidade": documento.get("capacidade"),
            }
            for documento in documentos
        ]

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar as tuas turmas.",
        }), 503

    return jsonify({
        "profissional": {
            "id": str(profissional["_id"]),
            "nome": g.utilizador.get("nome"),
            "perfil": g.utilizador["perfil"],
        },
        "turmas": turmas,
        "quantidade": len(turmas),
        "limite": 50,
    }), 200


@bp.get("/me/turmas/<turma_id>/alunos")
def listar_alunos_minha_turma(turma_id):
    """Lista os alunos de uma turma do profissional autenticado — devolve 404
    (não 403) se a turma existir mas não lhe pertencer, para não revelar a
    outros utilizadores quais turmas existem."""
    import models.aluno as modelo_aluno

    if not ObjectId.is_valid(turma_id):
        return jsonify({
            "error": "invalid_class_id",
            "message": "O identificador da turma é inválido.",
        }), 400

    profissional, erro = obter_profissional_da_sessao()

    if erro is not None:
        return erro

    try:
        turma = modelo_turma.obter_atribuida_ao_profissional(turma_id, profissional["_id"])

        if turma is None:
            return jsonify({
                "error": "class_not_accessible",
                "message": "A turma não existe ou não te está atribuída.",
            }), 404

        documentos = modelo_aluno.listar_por_turma(turma["_id"])

        alunos = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "numero_processo": documento.get("numero_processo"),
                "turma_id": str(turma["_id"]),
            }
            for documento in documentos
        ]

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar os alunos da turma.",
        }), 503

    return jsonify({
        "turma": {
            "id": str(turma["_id"]),
            "nome": turma.get("nome"),
            "ano_letivo": turma.get("ano_letivo"),
            "tipo": turma.get("tipo"),
            "capacidade": turma.get("capacidade"),
        },
        "alunos": alunos,
        "quantidade": len(alunos),
        "limite": 50,
    }), 200
