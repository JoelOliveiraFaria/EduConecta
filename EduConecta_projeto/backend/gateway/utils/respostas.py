"""Utilitário: respostas de erro no mesmo formato JSON dos serviços.

`{"error": "<codigo>", "message": "<texto>"}`, com o cabeçalho
WWW-Authenticate nos 401, como exige a especificação HTTP para desafios Bearer.
"""

from quart import jsonify


def erro(codigo, mensagem, estado, cabecalhos=None):
    resposta = jsonify({"error": codigo, "message": mensagem})
    if estado == 401:
        resposta.headers["WWW-Authenticate"] = "Bearer"
    for nome, valor in (cabecalhos or {}).items():
        resposta.headers[nome] = valor
    return resposta, estado
