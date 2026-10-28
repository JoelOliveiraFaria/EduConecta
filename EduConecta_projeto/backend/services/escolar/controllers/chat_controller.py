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
            aluno = modelo_aluno.obter_para_chat(aluno_oid, encarregado["_id"])

            if aluno is not None and isinstance(aluno.get("turma_id"), ObjectId):
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
