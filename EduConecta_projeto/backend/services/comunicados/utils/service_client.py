import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import jsonify, request


def erro(codigo, mensagem, estado):
    resposta = jsonify({
        "error": codigo,
        "message": mensagem,
    })

    if estado == 401:
        resposta.headers["WWW-Authenticate"] = "Bearer"

    return resposta, estado


def consultar_servico(url, metodo="GET", dados=None):
    headers = {
        "Authorization": request.headers.get("Authorization", ""),
        "Accept": "application/json",
    }

    corpo = None

    if dados is not None:
        headers["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode("utf-8")

    pedido = Request(
        url,
        data=corpo,
        headers=headers,
        method=metodo,
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
                "Sessão inválida ou expirada.",
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
            "Não foi possível validar o acesso.",
            503,
        )

    except (URLError, TimeoutError, OSError, ValueError):
        return None, erro(
            "dependency_unavailable",
            "Não foi possível contactar os serviços de acesso.",
            503,
        )
