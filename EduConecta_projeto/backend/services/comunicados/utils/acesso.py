from bson import ObjectId
from flask import g

from db import AUTH_URL, PERFIS_PUBLICACAO, SCHOOL_URL
from utils.service_client import consultar_servico, erro


def verificar_acesso(turma_id, publicar=False):
    if not ObjectId.is_valid(turma_id):
        return erro(
            "invalid_class_id",
            "O identificador da turma é inválido.",
            400,
        )

    turma_canonica = str(ObjectId(turma_id))

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

    perfil = conta.get("perfil")

    if perfil in PERFIS_PUBLICACAO:
        dados, falha = consultar_servico(
            f"{SCHOOL_URL}/me/turmas/{turma_canonica}/alunos"
        )

        if falha is not None:
            return falha

        if not isinstance(dados.get("alunos"), list):
            return erro(
                "dependency_unavailable",
                "O serviço escolar devolveu uma resposta inesperada.",
                503,
            )

    elif perfil == "encarregado" and not publicar:
        dados, falha = consultar_servico(
            f"{SCHOOL_URL}/me/alunos"
        )

        if falha is not None:
            return falha

        alunos = dados.get("alunos")

        if not isinstance(alunos, list):
            return erro(
                "dependency_unavailable",
                "O serviço escolar devolveu uma resposta inesperada.",
                503,
            )

        associado = any(
            isinstance(aluno, dict)
            and isinstance(aluno.get("turma_id"), str)
            and ObjectId.is_valid(aluno["turma_id"])
            and str(ObjectId(aluno["turma_id"])) == turma_canonica
            for aluno in alunos
        )

        if not associado:
            return erro(
                "class_not_accessible",
                "A turma não existe ou não está associada aos teus educandos.",
                404,
            )

    else:
        return erro(
            "forbidden",
            "O teu perfil não pode realizar esta operação.",
            403,
        )

    g.utilizador_id = str(ObjectId(conta["id"]))
    g.turma_id = turma_canonica
    return None


def obter_conta_chat():
    conta, falha = consultar_servico(f"{AUTH_URL}/me")

    if falha is not None:
        return None, falha

    if (
        conta.get("estado") != "ativo"
        or not isinstance(conta.get("id"), str)
        or not ObjectId.is_valid(conta["id"])
        or conta.get("perfil") not in {
            "docente",
            "educadora",
            "encarregado",
        }
    ):
        return None, erro(
            "forbidden",
            "Esta operação exige uma conta autorizada para o chat.",
            403,
        )

    return conta, None


def validar_relacao_chat(conta, contexto):
    if conta["perfil"] in {"docente", "educadora"}:
        participante = contexto["profissional_utilizador_id"]
    else:
        participante = contexto["encarregado_utilizador_id"]

    if str(ObjectId(conta["id"])) != participante:
        return None, erro(
            "forbidden",
            "Só podes aceder a conversas em que participas.",
            403,
        )

    validacao, falha = consultar_servico(
        f"{SCHOOL_URL}/me/chat/validar",
        metodo="POST",
        dados=contexto,
    )

    if falha is not None:
        return None, falha

    if (
        validacao.get("autorizado") is not True
        or any(
            validacao.get(campo) != contexto[campo]
            for campo in contexto
        )
        or not isinstance(validacao.get("turma_id"), str)
        or not ObjectId.is_valid(validacao["turma_id"])
    ):
        return None, erro(
            "dependency_unavailable",
            "O serviço escolar devolveu uma validação inesperada.",
            503,
        )

    return validacao, None
