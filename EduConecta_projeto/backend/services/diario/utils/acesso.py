"""Utilitário: comunicação com os serviços auth e escolar.

O diario não tem a sua própria noção de "quem pode o quê" — pergunta sempre
ao auth quem está autenticado e ao escolar se essa pessoa tem acesso à
turma/aluno em causa. Nenhuma lógica de negócio do diario vive aqui.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bson import ObjectId
from flask import g, jsonify, request

from db import AUTH_URL, SCHOOL_URL


def erro(codigo, mensagem, estado):
    """Monta uma resposta de erro JSON consistente; acrescenta o cabeçalho
    WWW-Authenticate quando o estado é 401, como o protocolo HTTP espera."""
    resposta = jsonify({
        "error": codigo,
        "message": mensagem,
    })

    if estado == 401:
        resposta.headers["WWW-Authenticate"] = "Bearer"

    return resposta, estado


def consultar_servico(url):
    """Chama um endpoint interno de outro serviço, reenviando o cabeçalho
    Authorization do pedido original (propaga a sessão do utilizador).

    Devolve (dados, None) em caso de sucesso, ou (None, resposta_de_erro) já
    pronta a devolver ao cliente — os códigos HTTP do serviço remoto são
    traduzidos para mensagens do diario, sem nunca mostrar detalhes internos.
    """
    pedido = Request(
        url,
        headers={
            "Authorization": request.headers.get("Authorization", ""),
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(pedido, timeout=5) as resposta:
            dados = json.load(resposta)

        if not isinstance(dados, dict):
            raise ValueError("Resposta inesperada.")

        return dados, None

    except HTTPError as exc:
        if exc.code == 401:
            return None, erro(
                "authentication_required",
                "Sessão inválida ou expirada. Inicia sessão novamente.",
                401,
            )

        if exc.code == 403:
            return None, erro(
                "forbidden",
                "A conta não tem autorização para esta operação.",
                403,
            )

        if exc.code == 404:
            return None, erro(
                "resource_not_accessible",
                "O recurso não existe ou não está acessível.",
                404,
            )

        return None, erro(
            "dependency_unavailable",
            "Não foi possível validar o acesso. Tenta novamente.",
            503,
        )

    except (URLError, TimeoutError, OSError, ValueError):
        return None, erro(
            "dependency_unavailable",
            "Não foi possível contactar os serviços de acesso.",
            503,
        )


def verificar_acesso(turma_id, aluno_id):
    """Confirma que quem está autenticado pode escrever/ler o Diário deste par
    turma+aluno.

    Dois passos sequenciais: (1) o auth confirma que a conta está ativa e tem
    perfil profissional (docente/educadora/auxiliar); (2) o escolar confirma
    que esse profissional está mesmo atribuído a esta turma e que o aluno
    pertence a ela. Como efeito colateral, guarda o id do utilizador em
    `g.utilizador_id` para as rotas usarem (ex: campo `criado_por`).
    Devolve None se o acesso é permitido, ou a resposta de erro a devolver.
    """
    if not ObjectId.is_valid(turma_id):
        return erro(
            "invalid_class_id",
            "O identificador da turma é inválido.",
            400,
        )

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
        or conta.get("perfil") not in {"docente", "educadora", "auxiliar"}
        or not isinstance(conta.get("id"), str)
        or not ObjectId.is_valid(conta["id"])
    ):
        return erro(
            "forbidden",
            "Esta operação exige uma conta profissional ativa.",
            403,
        )

    dados, falha = consultar_servico(
        f"{SCHOOL_URL}/me/turmas/{turma_id}/alunos"
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

    aluno_canonico = str(ObjectId(aluno_id))

    if not any(
        isinstance(aluno, dict)
        and aluno.get("id") == aluno_canonico
        for aluno in alunos
    ):
        return erro(
            "student_not_accessible",
            "O aluno não foi encontrado entre os alunos acessíveis da turma.",
            404,
        )

    g.utilizador_id = conta["id"]
    return None
