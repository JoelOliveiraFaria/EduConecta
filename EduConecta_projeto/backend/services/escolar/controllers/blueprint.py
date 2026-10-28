from bson import ObjectId
from flask import Blueprint, g, jsonify, request

from utils.auth_client import obter_utilizador_da_sessao

bp = Blueprint("escolar", __name__)

PERMISSOES_PESSOAIS = {
    "escolar.listar_meus_alunos": {"encarregado"},
    "escolar.listar_minhas_turmas": {"docente", "educadora", "auxiliar"},
    "escolar.listar_alunos_minha_turma": {"docente", "educadora", "auxiliar"},
    "escolar.validar_participantes_chat": {"docente", "educadora", "encarregado"},
}


@bp.before_request
def verificar_acesso_escolar():
    if request.endpoint is None:
        return None

    autorizacao = request.headers.get("Authorization", "")
    partes = autorizacao.split()

    if len(autorizacao) > 8192 or len(partes) != 2 or partes[0].lower() != "bearer":
        return jsonify({
            "error": "authentication_required",
            "message": "É necessário iniciar sessão.",
        }), 401, {"WWW-Authenticate": "Bearer"}

    utilizador, erro = obter_utilizador_da_sessao(partes[1])

    if erro is not None:
        return erro

    g.utilizador = utilizador

    if request.endpoint in PERMISSOES_PESSOAIS:
        if utilizador["perfil"] in PERMISSOES_PESSOAIS[request.endpoint]:
            return None

    elif utilizador["perfil"] == "admin":
        return None

    return jsonify({
        "error": "forbidden",
        "message": "Não tens permissão para realizar esta operação.",
    }), 403


@bp.after_request
def impedir_cache_dados_escolares(resposta):
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def obter_profissional_da_sessao():
    import models.profissional as modelo_profissional

    profissional = modelo_profissional.obter_por_utilizador(ObjectId(g.utilizador["id"]))

    if profissional is None:
        return None, (
            jsonify({
                "error": "professional_profile_not_linked",
                "message": "A conta ainda não tem um registo profissional associado.",
            }),
            403,
        )

    if (
        g.utilizador.get("perfil") not in {"docente", "educadora", "auxiliar"}
        or profissional.get("perfil") != g.utilizador["perfil"]
    ):
        return None, (
            jsonify({
                "error": "professional_profile_mismatch",
                "message": "O perfil da conta não corresponde ao registo profissional.",
            }),
            403,
        )

    return profissional, None
