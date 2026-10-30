"""Controller: endpoint interno (Fase 2), chamado só pelo consumidor do
serviço `notificacoes` para resolver quem deve ser avisado sobre eventos de
uma turma — nunca pelo cliente final.

Fica num blueprint próprio (como health_controller) para ficar de fora do
`before_request` do blueprint `escolar`, que exige sempre uma sessão de
utilizador: aqui a autenticação é outra — um segredo partilhado entre
serviços (`X-Internal-Key`), porque quem chama é o próprio backend
`notificacoes`, sem token de utilizador nenhum (está a processar uma
mensagem do RabbitMQ, não um pedido HTTP de alguém).
"""

import hmac
import os

from bson import ObjectId
from flask import Blueprint, jsonify, request

import models.aluno as modelo_aluno
import models.encarregado as modelo_encarregado
import models.profissional as modelo_profissional
import models.turma as modelo_turma

bp = Blueprint("interno", __name__)


def _chave_valida():
    esperada = os.environ.get("INTERNAL_SERVICE_KEY", "")
    recebida = request.headers.get("X-Internal-Key", "")
    return bool(esperada) and hmac.compare_digest(esperada, recebida)


@bp.get("/internal/turmas/<turma_id>/destinatarios")
def destinatarios_turma(turma_id):
    """Devolve os utilizador_id dos profissionais atribuídos à turma e dos
    encarregados de educação dos seus alunos — os dois grupos que o serviço
    `notificacoes` pode precisar de avisar por causa de um evento desta
    turma (comunicado publicado, justificação submetida/decidida)."""
    if not _chave_valida():
        return jsonify({
            "error": "forbidden",
            "message": "Chave interna inválida ou em falta.",
        }), 403

    if not ObjectId.is_valid(turma_id):
        return jsonify({
            "error": "invalid_class_id",
            "message": "O identificador da turma é inválido.",
        }), 400

    profissionais_ids = modelo_turma.profissionais_atribuidos(turma_id)

    if profissionais_ids is None:
        return jsonify({
            "error": "class_not_found",
            "message": "Turma não encontrada.",
        }), 404

    profissionais_utilizador_ids = [
        str(p["utilizador_id"])
        for p in modelo_profissional.listar_por_ids(profissionais_ids)
        if p.get("utilizador_id") is not None
    ]

    encarregados_ids = modelo_aluno.listar_encarregados_ids_por_turma(turma_id)
    encarregados_utilizador_ids = [
        str(e["utilizador_id"])
        for e in modelo_encarregado.listar_por_ids(encarregados_ids)
        if e.get("utilizador_id") is not None
    ]

    return jsonify({
        "turma_id": turma_id,
        "profissionais_utilizador_ids": profissionais_utilizador_ids,
        "encarregados_utilizador_ids": encarregados_utilizador_ids,
    }), 200


@bp.get("/internal/alunos/<aluno_id>/destinatarios")
def destinatarios_aluno(aluno_id):
    """Devolve o nome do aluno e os utilizador_id dos seus encarregados de
    educação — para eventos que dizem respeito a um só aluno (ex: falta
    registada), em que avisar os encarregados da turma inteira seria errado."""
    if not _chave_valida():
        return jsonify({
            "error": "forbidden",
            "message": "Chave interna inválida ou em falta.",
        }), 403

    if not ObjectId.is_valid(aluno_id):
        return jsonify({
            "error": "invalid_student_id",
            "message": "O identificador do aluno é inválido.",
        }), 400

    aluno = modelo_aluno.obter_com_encarregados(aluno_id)

    if aluno is None:
        return jsonify({
            "error": "student_not_found",
            "message": "Aluno não encontrado.",
        }), 404

    encarregados_utilizador_ids = [
        str(e["utilizador_id"])
        for e in modelo_encarregado.listar_por_ids(aluno.get("encarregados_ids", []))
        if e.get("utilizador_id") is not None
    ]

    return jsonify({
        "aluno_id": aluno_id,
        "aluno_nome": aluno.get("nome"),
        "encarregados_utilizador_ids": encarregados_utilizador_ids,
    }), 200
