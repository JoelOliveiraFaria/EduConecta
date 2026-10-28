from datetime import date, datetime, timezone

from bson import ObjectId
from flask import Blueprint, g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.registo as modelo_registo
from db import CAMPOS_TEXTO, AUTH_URL, SCHOOL_URL
from utils.acesso import consultar_servico, erro, verificar_acesso

bp = Blueprint("diario", __name__)


@bp.after_request
def impedir_cache(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@bp.post("/turmas/<turma_id>/alunos/<aluno_id>/diario")
def criar_registo(turma_id, aluno_id):
    falha = verificar_acesso(turma_id, aluno_id)

    if falha is not None:
        return falha

    if not request.is_json:
        return erro(
            "unsupported_media_type",
            "Envia Content-Type: application/json.",
            415,
        )

    dados = request.get_json(silent=True)
    campos = {"data", *CAMPOS_TEXTO}

    if not isinstance(dados, dict) or set(dados) != campos:
        return erro(
            "invalid_fields",
            "Envia apenas data, alimentacao, sono, higiene, "
            "atividades e observacoes. Todos os campos são obrigatórios.",
            400,
        )

    data_texto = dados["data"]

    try:
        if not isinstance(data_texto, str):
            raise ValueError

        data_registo = date.fromisoformat(data_texto)

        if data_registo.isoformat() != data_texto:
            raise ValueError

    except ValueError:
        return erro(
            "invalid_date",
            "A data deve ter o formato AAAA-MM-DD e ser válida.",
            400,
        )

    textos = {}

    for campo in CAMPOS_TEXTO:
        valor = dados[campo]

        if not isinstance(valor, str) or len(valor) > 2000:
            return erro(
                "invalid_text",
                f"O campo {campo} deve ser texto com até 2000 caracteres.",
                400,
            )

        textos[campo] = valor.strip()

    if not any(textos.values()):
        return erro(
            "empty_record",
            "Preenche pelo menos um dos campos do Diário.",
            400,
        )

    aluno_canonico = str(ObjectId(aluno_id))
    turma_canonica = str(ObjectId(turma_id))

    documento = {
        "_id": f"{aluno_canonico}:{data_texto}",
        "aluno_id": aluno_canonico,
        "turma_id": turma_canonica,
        "data": data_texto,
        **textos,
        "criado_por": g.utilizador_id,
        "criado_em": datetime.now(timezone.utc),
    }

    try:
        modelo_registo.inserir(documento)

    except DuplicateKeyError:
        return erro(
            "daily_record_already_exists",
            "Já existe um registo para este aluno nesta data.",
            409,
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível guardar o registo.",
            503,
        )

    return jsonify(modelo_registo.serializar(documento)), 201


@bp.get("/turmas/<turma_id>/alunos/<aluno_id>/diario")
def listar_registos(turma_id, aluno_id):
    falha = verificar_acesso(turma_id, aluno_id)

    if falha is not None:
        return falha

    try:
        documentos = modelo_registo.listar_por_aluno_turma(
            str(ObjectId(aluno_id)), str(ObjectId(turma_id))
        )

        registos = [
            modelo_registo.serializar(documento)
            for documento in documentos
        ]

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar os registos.",
            503,
        )

    return jsonify({
        "registos": registos,
        "quantidade": len(registos),
        "limite": 31,
    }), 200


@bp.get("/me/alunos/<aluno_id>/diario")
def listar_diario_meu_educando(aluno_id):
    if not ObjectId.is_valid(aluno_id):
        return erro(
            "invalid_student_id",
            "O identificador do aluno é inválido.",
            400,
        )

    conta, falha = consultar_servico(f"{AUTH_URL}/me")

    if falha is not None:
        return falha

    if (
        conta.get("estado") != "ativo"
        or not isinstance(conta.get("id"), str)
        or not ObjectId.is_valid(conta["id"])
    ):
        return erro(
            "invalid_session",
            "Não foi possível validar a conta.",
            401,
        )

    if conta.get("perfil") != "encarregado":
        return erro(
            "forbidden",
            "Esta consulta destina-se a encarregados de educação.",
            403,
        )

    dados, falha = consultar_servico(f"{SCHOOL_URL}/me/alunos")

    if falha is not None:
        return falha

    alunos = dados.get("alunos")

    if not isinstance(alunos, list):
        return erro(
            "dependency_unavailable",
            "O serviço escolar devolveu uma resposta inesperada.",
            503,
        )

    aluno_canonico = str(ObjectId(aluno_id))

    aluno = next(
        (
            item
            for item in alunos
            if isinstance(item, dict)
            and item.get("id") == aluno_canonico
        ),
        None,
    )

    if aluno is None:
        return erro(
            "student_not_accessible",
            "O aluno não existe ou não está associado à tua conta.",
            404,
        )

    turma_id = aluno.get("turma_id")

    if not isinstance(turma_id, str) or not ObjectId.is_valid(turma_id):
        return erro(
            "student_class_not_linked",
            "O aluno ainda não tem uma turma válida associada.",
            404,
        )

    try:
        documentos = modelo_registo.listar_por_aluno_turma(
            aluno_canonico, str(ObjectId(turma_id))
        )

        registos = []

        for documento in documentos:
            registo = modelo_registo.serializar(documento)
            registo.pop("criado_por", None)
            registos.append(registo)

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível consultar o Diário do educando.",
            503,
        )

    return jsonify({
        "aluno": {
            "id": aluno_canonico,
            "nome": aluno.get("nome"),
            "turma_id": str(ObjectId(turma_id)),
        },
        "registos": registos,
        "quantidade": len(registos),
        "limite": 31,
    }), 200


@bp.patch("/turmas/<turma_id>/alunos/<aluno_id>/diario/<data_registo>")
def editar_registo(turma_id, aluno_id, data_registo):
    falha = verificar_acesso(turma_id, aluno_id)

    if falha is not None:
        return falha

    try:
        data_validada = date.fromisoformat(data_registo)

        if data_validada.isoformat() != data_registo:
            raise ValueError

    except ValueError:
        return erro(
            "invalid_date",
            "A data deve ter o formato AAAA-MM-DD e ser válida.",
            400,
        )

    if not request.is_json:
        return erro(
            "unsupported_media_type",
            "Envia Content-Type: application/json.",
            415,
        )

    dados = request.get_json(silent=True)

    if (
        not isinstance(dados, dict)
        or not dados
        or set(dados) - set(CAMPOS_TEXTO)
    ):
        return erro(
            "invalid_fields",
            "Envia um ou mais campos: alimentacao, sono, "
            "higiene, atividades e observacoes.",
            400,
        )

    alteracoes = {}

    for campo, valor in dados.items():
        if not isinstance(valor, str) or len(valor) > 2000:
            return erro(
                "invalid_text",
                f"O campo {campo} deve ser texto com até 2000 caracteres.",
                400,
            )

        alteracoes[campo] = valor.strip()

    if not any(alteracoes.values()):
        return erro(
            "empty_update",
            "Inclui pelo menos um campo com texto nesta edição.",
            400,
        )

    aluno_canonico = str(ObjectId(aluno_id))

    alteracoes["atualizado_em"] = datetime.now(timezone.utc)
    alteracoes["atualizado_por"] = g.utilizador_id

    try:
        documento = modelo_registo.atualizar(
            aluno_canonico,
            str(ObjectId(turma_id)),
            data_registo,
            g.utilizador_id,
            alteracoes,
        )

    except PyMongoError:
        return erro(
            "database_unavailable",
            "Não foi possível atualizar o registo.",
            503,
        )

    if documento is None:
        return erro(
            "record_not_editable",
            "O registo não existe ou não pode ser editado por esta conta.",
            404,
        )

    resposta = modelo_registo.serializar(documento)
    resposta["atualizado_em"] = documento["atualizado_em"].isoformat(
        timespec="milliseconds"
    )
    resposta["atualizado_por"] = documento["atualizado_por"]

    return jsonify(resposta), 200
