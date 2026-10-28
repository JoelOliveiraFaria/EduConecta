"""Utilitário: chamadas HTTP ao serviço auth (fora do processo, via rede Docker).

Isto não é um model — não acede à base de dados deste serviço, só fala com
outro serviço. Fica em utils/ porque é uma dependência externa partilhada
por vários controllers, não lógica de negócio do escolar.
"""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bson import ObjectId
from flask import jsonify


def obter_utilizador_da_sessao(token):
    """Valida um token junto do auth (GET /me); usado pelo before_request do
    blueprint para autenticar TODOS os pedidos a este serviço."""
    pedido = Request(
        "http://auth:8000/me",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )

    try:
        with urlopen(pedido, timeout=5) as resposta:
            utilizador = json.loads(resposta.read().decode("utf-8"))

    except HTTPError as erro:
        codigo = erro.code
        erro.close()

        if codigo == 401:
            return None, (
                jsonify({
                    "error": "invalid_session",
                    "message": "Sessão inválida ou expirada. Inicia sessão novamente.",
                }),
                401,
                {"WWW-Authenticate": "Bearer"},
            )

        if codigo == 403:
            return None, (
                jsonify({
                    "error": "account_inactive",
                    "message": "A conta não está ativa.",
                }),
                403,
            )

        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "Não foi possível verificar a sessão.",
            }),
            503,
        )

    except (URLError, OSError, ValueError, UnicodeError):
        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "O serviço de autenticação não está disponível.",
            }),
            503,
        )

    if (
        not isinstance(utilizador, dict)
        or not isinstance(utilizador.get("id"), str)
        or not ObjectId.is_valid(utilizador["id"])
        or utilizador.get("estado") != "ativo"
        or not isinstance(utilizador.get("perfil"), str)
    ):
        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "Não foi possível validar a resposta da autenticação.",
            }),
            503,
        )

    return utilizador, None


def obter_conta_para_associacao(conta_id, autorizacao_header):
    """Consulta uma conta no auth (GET /admin/utilizadores/<id>) para a rota
    de associar conta a encarregado. Devolve 401 ("invalid_session") e 403
    ("forbidden") com mensagens DIFERENTES uma da outra.

    ATENÇÃO: esta função parece quase idêntica a
    `consultar_conta_profissional_auth` logo abaixo, mas NÃO são
    intercambiáveis — têm formas de erro diferentes porque servem chamadores
    diferentes que já esperavam essas formas antes do refactor para MVC.
    Isto foi uma decisão deliberada para preservar o comportamento exato do
    código original, não um esquecimento de duplicação a limpar. Se
    precisares de juntar as duas, confirma primeiro com quem chama cada uma
    que o novo formato de erro não vai partir nada."""
    pedido = Request(
        f"http://auth:8000/admin/utilizadores/{conta_id}",
        headers={"Authorization": autorizacao_header},
        method="GET",
    )

    try:
        with urlopen(pedido, timeout=5) as resposta:
            conta = json.loads(resposta.read().decode("utf-8"))

    except HTTPError as erro:
        codigo = erro.code
        erro.close()

        if codigo == 404:
            return None, (
                jsonify({
                    "error": "user_not_found",
                    "message": "A conta de utilizador não existe.",
                }),
                404,
            )

        if codigo == 401:
            return None, (
                jsonify({
                    "error": "invalid_session",
                    "message": "A sessão expirou. Inicia sessão novamente.",
                }),
                401,
                {"WWW-Authenticate": "Bearer"},
            )

        if codigo == 403:
            return None, (
                jsonify({
                    "error": "forbidden",
                    "message": "Não tens permissão para consultar essa conta.",
                }),
                403,
            )

        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "Não foi possível verificar a conta.",
            }),
            503,
        )

    except (URLError, OSError, ValueError, UnicodeError):
        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "O serviço de autenticação não está disponível.",
            }),
            503,
        )

    if not isinstance(conta, dict) or conta.get("id") != conta_id:
        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "A resposta da autenticação é inválida.",
            }),
            503,
        )

    return conta, None


def consultar_conta_profissional_auth(conta_id, autorizacao_header):
    """Consulta uma conta no auth (GET /admin/utilizadores/<id>) para as rotas
    de profissionais (criar_profissional, associar_profissional_turma).
    Agrupa 401 e 403 num único erro ("authorization_failed") — ver o aviso
    em `obter_conta_para_associacao` acima sobre porque esta função não foi
    fundida com essa."""
    pedido = Request(
        f"http://auth:8000/admin/utilizadores/{conta_id}",
        headers={"Authorization": autorizacao_header},
        method="GET",
    )

    try:
        with urlopen(pedido, timeout=5) as resposta:
            conta = json.loads(resposta.read().decode("utf-8"))

    except HTTPError as erro:
        codigo = erro.code
        erro.close()

        if codigo == 404:
            return None, (
                jsonify({
                    "error": "user_not_found",
                    "message": "A conta de utilizador não existe.",
                }),
                404,
            )

        if codigo in {401, 403}:
            return None, (
                jsonify({
                    "error": "authorization_failed",
                    "message": "Não foi possível autorizar esta operação.",
                }),
                codigo,
            )

        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "Não foi possível consultar a conta.",
            }),
            503,
        )

    except (URLError, OSError, ValueError, UnicodeError):
        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "O serviço de autenticação não está disponível.",
            }),
            503,
        )

    if not isinstance(conta, dict) or conta.get("id") != conta_id:
        return None, (
            jsonify({
                "error": "authentication_unavailable",
                "message": "A resposta da autenticação é inválida.",
            }),
            503,
        )

    return conta, None
