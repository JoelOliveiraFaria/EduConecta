"""Controller: valida se uma conversa de chat entre um profissional e um
encarregado, a propósito de um aluno concreto, é legítima.

Usado por outro serviço (comunicados) antes de permitir abrir/usar uma
conversa — não existe nenhuma coleção "chat" aqui; esta rota só confirma
que a relação escolar entre os três participantes existe.
"""

from bson import ObjectId
from flask import g, jsonify, request
from pymongo.errors import PyMongoError

import models.aluno as modelo_aluno
import models.encarregado as modelo_encarregado
import models.profissional as modelo_profissional
import models.turma as modelo_turma
from controllers.blueprint import bp


@bp.post("/me/chat/validar")
def validar_participantes_chat():
    """Confirma que a conta autenticada pode participar numa conversa sobre um aluno.

    Recebe aluno_id + profissional_utilizador_id + encarregado_utilizador_id
    e verifica a cadeia toda de relações, não só uma ponta:

      1. Participante: a conta autenticada tem de SER um dos dois
         participantes indicados (o profissional, se for docente/educadora,
         ou o encarregado, se for perfil encarregado) — ninguém pode validar
         uma conversa em que não está envolvido.
      2. Profissional ↔ encarregado ↔ aluno ↔ turma formam uma cadeia única
         que tem de fechar: o profissional tem de lecionar a turma do aluno,
         e o encarregado tem de ser mesmo encarregado desse aluno. Só
         validando a cadeia inteira é que se garante que o profissional e o
         encarregado têm uma razão legítima (o mesmo aluno, na mesma turma)
         para falar um com o outro.

    Devolve 403 se a conta não for participante válido, 404 se a cadeia de
    relações não fechar (ex: aluno não é educando deste encarregado, ou
    turma não é lecionada por este profissional), e 200 com autorizado=True
    se tudo bater certo.
    """
    if not request.is_json:
        return jsonify({
            "error": "unsupported_media_type",
            "message": "Envia Content-Type: application/json.",
        }), 415

    dados = request.get_json(silent=True)

    campos = {"aluno_id", "profissional_utilizador_id", "encarregado_utilizador_id"}

    if (
        not isinstance(dados, dict)
        or set(dados) != campos
        or any(
            not isinstance(dados[campo], str) or not ObjectId.is_valid(dados[campo])
            for campo in campos
        )
    ):
        return jsonify({
            "error": "invalid_fields",
            "message": (
                "Envia aluno_id, profissional_utilizador_id e "
                "encarregado_utilizador_id com identificadores válidos."
            ),
        }), 400

    aluno_oid = ObjectId(dados["aluno_id"])
    profissional_conta_oid = ObjectId(dados["profissional_utilizador_id"])
    encarregado_conta_oid = ObjectId(dados["encarregado_utilizador_id"])
    conta_atual_oid = ObjectId(g.utilizador["id"])

    perfil_atual = g.utilizador["perfil"]

    # A conta autenticada tem de corresponder a um dos dois IDs enviados no
    # pedido — nunca pode validar uma conversa alheia.
    if perfil_atual in {"docente", "educadora"}:
        participante_valido = conta_atual_oid == profissional_conta_oid
    elif perfil_atual == "encarregado":
        participante_valido = conta_atual_oid == encarregado_conta_oid
    else:
        participante_valido = False

    if not participante_valido or profissional_conta_oid == encarregado_conta_oid:
        return jsonify({
            "error": "forbidden",
            "message": "Só podes validar conversas em que participas.",
        }), 403

    try:
        profissional = modelo_profissional.obter_para_chat(profissional_conta_oid)
        encarregado = modelo_encarregado.obter_para_chat(encarregado_conta_oid)

        aluno = None
        turma = None

        if profissional is not None and encarregado is not None:
            # Fecha a cadeia: o aluno tem de ser educando deste encarregado...
            aluno = modelo_aluno.obter_para_chat(aluno_oid, encarregado["_id"])

            if aluno is not None and isinstance(aluno.get("turma_id"), ObjectId):
                # ...e a turma desse aluno tem de ser lecionada por este profissional.
                turma = modelo_turma.obter_para_chat(aluno["turma_id"], profissional["_id"])

        if profissional is None or encarregado is None or aluno is None or turma is None:
            return jsonify({
                "error": "chat_not_accessible",
                "message": "A relação escolar não existe ou não permite esta conversa.",
            }), 404

        if (
            perfil_atual in {"docente", "educadora"}
            and profissional.get("perfil") != perfil_atual
        ):
            return jsonify({
                "error": "forbidden",
                "message": "O perfil da conta não corresponde ao registo profissional.",
            }), 403

    except PyMongoError:
        return jsonify({
            "error": "database_unavailable",
            "message": "Não foi possível validar os participantes.",
        }), 503

    return jsonify({
        "autorizado": True,
        "aluno_id": str(aluno_oid),
        "turma_id": str(turma["_id"]),
        "profissional_utilizador_id": str(profissional_conta_oid),
        "encarregado_utilizador_id": str(encarregado_conta_oid),
    }), 200
