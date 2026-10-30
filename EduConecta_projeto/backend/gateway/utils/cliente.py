"""Utilitário: cliente HTTP partilhado para falar com os serviços.

Um único `httpx.AsyncClient` por processo, criado no primeiro uso, para
reaproveitar ligações. Os testes substituem o transporte
(`app.config["HTTP_TRANSPORT"]`) por um falso, sem rede.
"""

import httpx

TIMEOUT_PADRAO = httpx.Timeout(30.0, connect=5.0)


def obter_cliente(app):
    cliente = app.extensions.get("cliente_http")
    if cliente is None:
        cliente = httpx.AsyncClient(
            transport=app.config.get("HTTP_TRANSPORT"),
            follow_redirects=False,
            timeout=TIMEOUT_PADRAO,
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=40),
        )
        app.extensions["cliente_http"] = cliente
    return cliente


async def fechar_cliente(app):
    cliente = app.extensions.pop("cliente_http", None)
    if cliente is not None:
        await cliente.aclose()
