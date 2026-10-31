"""Controller: rotas de gestão de alunos (CRUD, associação a turma/encarregados).

Todas as rotas daqui passam primeiro por `verificar_acesso_escolar`
(controllers/blueprint.py). A maioria exige admin; exceções: /me/alunos
(encarregado) e, desde a Fase 1, PATCH /alunos/<id> (também aberto a um
profissional, limitado à sua própria turma).
"""

from bson import ObjectId
from flask import g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.aluno as modelo_aluno
import models.encarregado as modelo_encarregado
import models.turma as modelo_turma
from controllers.blueprint import bp, obter_profissional_da_sessao
from utils.eventos import publicar
from utils.validacao import validar_data_nascimento, validar_morada


@bp.get("/alunos")
def listar_alunos():
    """Lista até 50 alunos."""
    try:
        documentos = modelo_aluno.listar()

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
            "message": "Não foi possível consultar os alunos.",
        }), 503

    return jsonify({
        "alunos": alunos,
        "quantidade": len(alunos),
        "limite": 50,
    }), 200


@bp.post("/alunos")
def criar_aluno():
    """Cria um aluno (nome + numero_processo obrigatórios e únicos por
    processo; data_nascimento e morada são opcionais)."""
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

    campos_permitidos = {"nome", "numero_processo", "data_nascimento", "morada"}

    if set(dados) - campos_permitidos:
        return jsonify({
            "error": "unknown_fields",
            "message": (
                "Os campos permitidos são nome, numero_processo "
                "(obrigatórios), data_nascimento e morada (opcionais)."
            ),
        }), 400

    nome = dados.get("nome")
    numero_processo = dados.get("numero_processo")
    data_nascimento = dados.get("data_nascimento")
    morada = dados.get("morada", "")

    if not isinstance(nome, str) or not 2 <= len(nome.strip()) <= 150:
        return jsonify({
            "error": "invalid_name",
            "message": "O nome deve ser texto com 2 a 150 caracteres.",
        }), 400

    if not isinstance(numero_processo, str) or not 1 <= len(numero_processo.strip()) <= 50:
        return jsonify({
            "error": "invalid_process_number",
            "message": "O número de processo deve ser texto com 1 a 50 caracteres.",
        }), 400

    if data_nascimento is not None and not validar_data_nascimento(data_nascimento):
        return jsonify({
            "error": "invalid_birth_date",
            "message": "A data de nascimento deve ter o formato AAAA-MM-DD e não pode ser no futuro.",
        }), 400

    if not validar_morada(morada):
        return jsonify({
            "error": "invalid_address",
            "message": "A morada deve ser texto com até 200 caracteres.",
        }), 400

    try:
        inserted_id, aluno = modelo_aluno.criar(
            nome.strip(), numero_processo.strip(), data_nascimento, morada.strip()
        )

    except DuplicateKeyError:
        return jsonify({
            "error": "duplicate_process_number",
            "message": "Já existe um aluno com esse número de processo.",
        }), 409

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível guardar o aluno.",
        }), 503

    return jsonify({
        "id": str(inserted_id),
        "nome": aluno["nome"],
        "numero_processo": aluno["numero_processo"],
        "data_nascimento": aluno["data_nascimento"],
        "morada": aluno["morada"],
    }), 201


@bp.get("/alunos/<aluno_id>")
def obter_aluno(aluno_id):
    """Devolve um aluno pelo id."""
    if not ObjectId.is_valid(aluno_id):
        return jsonify({
            "error": "invalid_student_id",
            "message": "O identificador do aluno é inválido.",
        }), 400

    try:
        aluno = modelo_aluno.obter(aluno_id)

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar o aluno.",
        }), 503

    if aluno is None:
        return jsonify({
            "error": "student_not_found",
            "message": "Aluno não encontrado.",
        }), 404

    return jsonify({
        "id": str(aluno["_id"]),
        "nome": aluno.get("nome"),
        "numero_processo": aluno.get("numero_processo"),
        "data_nascimento": aluno.get("data_nascimento"),
        "morada": aluno.get("morada", ""),
    }), 200


@bp.patch("/alunos/<aluno_id>")
def atualizar_aluno(aluno_id):
    """Atualiza parcialmente nome e/ou numero_processo de um aluno.

    RF09: além do admin, um profissional (docente/educadora/auxiliar) pode
    editar um aluno, mas só se o aluno estiver numa turma onde esse
    profissional está atribuído (RNF01 — acesso limitado à própria turma).
    """
    if not ObjectId.is_valid(aluno_id):
        return jsonify({
            "error": "invalid_student_id",
            "message": "O identificador do aluno é inválido.",
        }), 400

    if g.utilizador["perfil"] != "admin":
        aluno_atual = modelo_aluno.obter(aluno_id)

        if aluno_atual is None:
            return jsonify({
                "error": "student_not_found",
                "message": "Aluno não encontrado.",
            }), 404

        turma_id = aluno_atual.get("turma_id")

        profissional, erro = obter_profissional_da_sessao()

        if erro is not None:
            return erro

        if turma_id is None or not modelo_turma.esta_atribuido(turma_id, profissional["_id"]):
            return jsonify({
                "error": "forbidden",
                "message": "Só podes editar alunos da tua própria turma.",
            }), 403

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

    if not dados:
        return jsonify({
            "error": "empty_update",
            "message": "Envia pelo menos um campo para atualizar.",
        }), 400

    campos_permitidos = {"nome", "numero_processo", "data_nascimento", "morada"}

    if set(dados) - campos_permitidos:
        return jsonify({
            "error": "unknown_fields",
            "message": "Os campos permitidos são nome, numero_processo, data_nascimento e morada.",
        }), 400

    alteracoes = {}

    if "nome" in dados:
        nome = dados["nome"]

        if not isinstance(nome, str) or not 2 <= len(nome.strip()) <= 150:
            return jsonify({
                "error": "invalid_name",
                "message": "O nome deve ser texto com 2 a 150 caracteres.",
            }), 400

        alteracoes["nome"] = nome.strip()

    if "numero_processo" in dados:
        numero_processo = dados["numero_processo"]

        if not isinstance(numero_processo, str) or not 1 <= len(numero_processo.strip()) <= 50:
            return jsonify({
                "error": "invalid_process_number",
                "message": "O número de processo deve ser texto com 1 a 50 caracteres.",
            }), 400

        alteracoes["numero_processo"] = numero_processo.strip()

    if "data_nascimento" in dados:
        data_nascimento = dados["data_nascimento"]

        if data_nascimento is not None and not validar_data_nascimento(data_nascimento):
            return jsonify({
                "error": "invalid_birth_date",
                "message": "A data de nascimento deve ter o formato AAAA-MM-DD e não pode ser no futuro.",
            }), 400

        alteracoes["data_nascimento"] = data_nascimento

    if "morada" in dados:
        morada = dados["morada"]

        if not validar_morada(morada):
            return jsonify({
                "error": "invalid_address",
                "message": "A morada deve ser texto com até 200 caracteres.",
            }), 400

        alteracoes["morada"] = morada.strip()

    try:
        aluno = modelo_aluno.atualizar(aluno_id, alteracoes)

    except DuplicateKeyError:
        return jsonify({
            "error": "duplicate_process_number",
            "message": "Já existe um aluno com esse número de processo.",
        }), 409

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível atualizar o aluno.",
        }), 503

    if aluno is None:
        return jsonify({
            "error": "student_not_found",
            "message": "Aluno não encontrado.",
        }), 404

    return jsonify({
        "id": str(aluno["_id"]),
        "nome": aluno.get("nome"),
        "numero_processo": aluno.get("numero_processo"),
        "data_nascimento": aluno.get("data_nascimento"),
        "morada": aluno.get("morada", ""),
    }), 200


@bp.delete("/alunos/<aluno_id>")
def eliminar_aluno(aluno_id):
    """Elimina um aluno (RF10) — soft delete, admin apenas.

    O documento não é removido da base de dados, só marcado como eliminado;
    deixa de aparecer em qualquer listagem/consulta normal a partir daqui.
    Os registos históricos noutros serviços (diario, assiduidade) que
    referenciam este aluno_id não são tocados — ficam como estavam.
    """
    if not ObjectId.is_valid(aluno_id):
        return jsonify({
            "error": "invalid_student_id",
            "message": "O identificador do aluno é inválido.",
        }), 400

    try:
        aluno = modelo_aluno.eliminar(aluno_id, ObjectId(g.utilizador["id"]))

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível eliminar o aluno.",
        }), 503

    if aluno is None:
        return jsonify({
            "error": "student_not_found",
            "message": "Aluno não encontrado.",
        }), 404

    publicar("aluno.eliminado", {"aluno_id": str(aluno["_id"])})

    return jsonify({
        "id": str(aluno["_id"]),
        "eliminado": True,
    }), 200


@bp.put("/alunos/<aluno_id>/turma")
def associar_aluno_turma(aluno_id):
    """Atribui (ou substitui) a turma de um aluno."""
    if not ObjectId.is_valid(aluno_id):
        return jsonify({
            "error": "invalid_student_id",
            "message": "O identificador do aluno é inválido.",
        }), 400

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

    if set(dados) != {"turma_id"}:
        return jsonify({
            "error": "invalid_fields",
            "message": "Envia apenas o campo obrigatório turma_id.",
        }), 400

    turma_id = dados["turma_id"]

    if not isinstance(turma_id, str) or not ObjectId.is_valid(turma_id):
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

        aluno = modelo_aluno.definir_turma(aluno_id, turma["_id"])

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível associar o aluno à turma.",
        }), 503

    if aluno is None:
        return jsonify({
            "error": "student_not_found",
            "message": "Aluno não encontrado.",
        }), 404

    return jsonify({
        "id": str(aluno["_id"]),
        "nome": aluno.get("nome"),
        "numero_processo": aluno.get("numero_processo"),
        "turma": {
            "id": str(turma["_id"]),
            "nome": turma.get("nome"),
            "ano_letivo": turma.get("ano_letivo"),
        },
    }), 200


@bp.put("/alunos/<aluno_id>/encarregados/<encarregado_id>")
def associar_encarregado_aluno(aluno_id, encarregado_id):
    """Liga um encarregado de educação a um aluno (um aluno pode ter vários)."""
    if not ObjectId.is_valid(aluno_id):
        return jsonify({
            "error": "invalid_student_id",
            "message": "O identificador do aluno é inválido.",
        }), 400

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

        aluno = modelo_aluno.adicionar_encarregado(aluno_id, encarregado["_id"])

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível associar o encarregado ao aluno.",
        }), 503

    if aluno is None:
        return jsonify({
            "error": "student_not_found",
            "message": "Aluno não encontrado.",
        }), 404

    return jsonify({
        "aluno": {
            "id": str(aluno["_id"]),
            "nome": aluno.get("nome"),
        },
        "encarregado": {
            "id": str(encarregado["_id"]),
            "nome": encarregado.get("nome"),
        },
        "message": "Associação confirmada.",
    }), 200


@bp.get("/alunos/<aluno_id>/encarregados")
def listar_encarregados_aluno(aluno_id):
    """Lista os encarregados de educação associados a um aluno."""
    if not ObjectId.is_valid(aluno_id):
        return jsonify({
            "error": "invalid_student_id",
            "message": "O identificador do aluno é inválido.",
        }), 400

    try:
        aluno = modelo_aluno.obter_com_encarregados(aluno_id)

        if aluno is None:
            return jsonify({
                "error": "student_not_found",
                "message": "Aluno não encontrado.",
            }), 404

        documentos = modelo_encarregado.listar_por_ids(aluno.get("encarregados_ids", []))

        encarregados = [
            {
                "id": str(documento["_id"]),
                "nome": documento.get("nome"),
                "cc": documento.get("cc", ""),
                "telemovel": documento.get("telemovel", ""),
                "morada": documento.get("morada", ""),
                "relacao": documento.get("relacao"),
            }
            for documento in documentos
        ]

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível consultar os encarregados do aluno.",
        }), 503

    return jsonify({
        "aluno": {
            "id": str(aluno["_id"]),
            "nome": aluno.get("nome"),
        },
        "encarregados": encarregados,
        "quantidade": len(encarregados),
        "limite": 50,
    }), 200


@bp.get("/me/alunos")
def listar_meus_alunos():
    """Lista os educandos do encarregado autenticado (rota pessoal, não precisa de admin)."""
    utilizador_id = ObjectId(g.utilizador["id"])

    try:
        encarregado = modelo_encarregado.obter_por_utilizador(utilizador_id)

        if encarregado is None:
            return jsonify({
                "error": "school_profile_not_linked",
                "message": "A conta ainda não tem um registo escolar associado.",
            }), 403

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
            "message": "Não foi possível consultar os teus educandos.",
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
