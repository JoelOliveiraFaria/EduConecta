"""Utilitário: respostas de erro padronizadas e chamada HTTP interna ao
serviço `auth`, para validar sessão de quem chama as rotas `/me/...`.

Reencaminha sempre o cabeçalho Authorization recebido do cliente — este
serviço nunca gera credenciais próprias, só propaga o token da sessão.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import jsonify, request


def erro(codigo, mensagem, estado):
    """Constrói a resposta JSON de erro padrão `{error, message}`.

    Acrescenta automaticamente o cabeçalho WWW-Authenticate em erros 401,
    como exige a especificação HTTP para desafios Bearer.
    """
    resposta = jsonify({"error": codigo, "message": mensagem})
    if estado == 401:
        resposta.headers["WWW-Authenticate"] = "Bearer"
    return resposta, estado


def consultar(url):
    """Chama um endpoint interno (auth) com o token do pedido atual.

    Devolve (dados, None) se a resposta for um JSON válido (objeto), ou
    (None, resposta_de_erro) já formatada para qualquer falha.
    """
    pedido = Request(url, headers={
        "Authorization": request.headers.get("Authorization", ""),
        "Accept": "application/json",
    })
    try:
        with urlopen(pedido, timeout=5) as resposta:
            dados = json.load(resposta)
        if not isinstance(dados, dict):
            raise ValueError()
        return dados, None
    except HTTPError as exc:
        codigo = exc.code
        exc.close()
        if codigo == 401:
            return None, erro("authentication_required", "Sessão inválida ou expirada.", 401)
        if codigo in {403, 404}:
            return None, erro("resource_not_accessible", "Recurso não acessível.", codigo)
        return None, erro("dependency_unavailable", "Serviço de acesso indisponível.", 503)
    except (URLError, OSError, TimeoutError, ValueError):
        return None, erro("dependency_unavailable", "Não foi possível validar o acesso.", 503)
