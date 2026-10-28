"""Utilitário: verificações de autorização que precisam de perguntar aos
outros serviços (auth para a sessão, escolar para as relações turma/aluno),
usadas pelos três controllers deste serviço (comunicados, anexos e chat).

Nada aqui acede à base de dados local — só confirma, via HTTP interno,
"quem é esta pessoa" e "a que é que ela tem direito", antes dos controllers
seguirem para os models.
"""

from bson import ObjectId
from flask import g

from db import AUTH_URL, PERFIS_PUBLICACAO, SCHOOL_URL
from utils.service_client import consultar_servico, erro


def verificar_acesso(turma_id, publicar=False):
    """Confirma que a conta autenticada pode ver (ou, se publicar=True,
    publicar em) os comunicados de uma turma, e deixa o resultado em
    g.utilizador_id / g.turma_id para o controller usar a seguir.

    Regras por perfil:
      - docente/educadora (PERFIS_PUBLICACAO): só precisam de estar
        atribuídos à turma (confirmado via GET /me/turmas/<id>/alunos no
        escolar) — podem ler e publicar.
      - encarregado, só para leitura (publicar=False): tem de ter um
        educando matriculado nessa turma (confirmado via GET /me/alunos).
      - qualquer outro perfil, ou um encarregado a tentar publicar: 403.
    """
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
    """Valida a sessão para uso no chat: conta ativa e com um dos três perfis
    que podem participar (docente, educadora, encarregado — note-se que
    auxiliar fica de fora de propósito, tal como em models/profissional.py)."""
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
    """Confirma que a conta autenticada é mesmo um dos participantes
    nomeados em `contexto`, e que a relação aluno/profissional/encarregado é
    real (ligação de turma, matrícula, atribuição) — perguntando ao serviço
    escolar (POST /me/chat/validar), não aos dados locais deste serviço, já
    que quem sabe essas relações é o escolar.

    Duas camadas de verificação, por ordem (a segunda só corre se a
    primeira passar, para não gastar um pedido HTTP com algo já recusável
    localmente):
      1. a conta tem de corresponder ao participante do seu próprio papel
         em `contexto` (um docente só pode validar-se a si mesmo como
         profissional, nunca personificar outro);
      2. o escolar confirma que aluno, profissional e encarregado estão de
         facto ligados entre si (mesma turma) — e a resposta é conferida
         campo a campo contra o `contexto` pedido, para recusar qualquer
         adulteração caso o escolar alguma vez devolva algo inesperado.

    Devolve (validacao, None) no sucesso — `validacao` inclui o turma_id
    resolvido pelo escolar, usado depois para etiquetar a conversa.
    """
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
