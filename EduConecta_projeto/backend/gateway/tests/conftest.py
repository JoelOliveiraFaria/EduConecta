import os
import time

SEGREDO = "segredo-de-teste-com-mais-de-32-caracteres"
os.environ["JWT_SECRET_KEY"] = SEGREDO

import httpx
import jwt
import pytest
import pytest_asyncio

from app import app as quart_app
from rotas import SERVICOS
from utils.limite import LimitadorJanelaFixa
from utils.saude import MonitorSaude

SUB = "6ae24e41252e5bf6b58984ab"


class _Fluxo(httpx.AsyncByteStream):
    """Corpo ainda não lido, como o de um serviço real. Com `content=` o MockTransport
    lê o corpo logo à cabeça e o gateway já não o conseguiria ler em streaming."""

    def __init__(self, corpo):
        self._corpo = corpo

    async def __aiter__(self):
        yield self._corpo


class ServicosFalsos:
    """Substitui os 6 serviços: responde 200 e regista cada pedido recebido.

    O serviço que recebeu o pedido é o nome do anfitrião do URL (http://auth:8000/...).
    """

    def __init__(self):
        self.pedidos = []
        self.erros = {}
        self.respostas = {}

    def __call__(self, pedido):
        servico = pedido.url.host
        self.pedidos.append(pedido)
        if servico in self.erros:
            raise self.erros[servico]
        estado, cabecalhos, corpo = self.respostas.get(servico, (200, {}, b"{}"))
        cabecalhos = {"x-stub-service": servico, "content-length": str(len(corpo)), **cabecalhos}
        return httpx.Response(estado, headers=cabecalhos, stream=_Fluxo(corpo))

    @property
    def ultimo(self):
        return self.pedidos[-1]

    def cabecalho_recebido(self, nome):
        return self.ultimo.headers.get(nome)


def fazer_token(segredo=SEGREDO, audiencia="educonecta-api", emissor="educonecta-auth",
                validade=900, sub=SUB, jti=True, iat=True, algoritmo="HS256"):
    """Gera um token como o auth o geraria; cada parâmetro permite estragar um aspeto."""
    agora = int(time.time())
    claims = {"iss": emissor, "aud": audiencia, "exp": agora + validade}
    if sub is not None:
        claims["sub"] = sub
    if jti:
        claims["jti"] = "a" * 32
    if iat:
        claims["iat"] = agora
    return jwt.encode(claims, segredo, algorithm=algoritmo)


@pytest.fixture
def token():
    return fazer_token


@pytest.fixture
def cabecalhos_auth():
    return {"Authorization": f"Bearer {fazer_token()}"}


@pytest.fixture
def app():
    quart_app.config["TESTING"] = True
    return quart_app


@pytest_asyncio.fixture
async def servicos(app):
    """Serviços falsos, limites altos e estado limpo em cada teste."""
    falsos = ServicosFalsos()
    app.config["HTTP_TRANSPORT"] = httpx.MockTransport(falsos)
    app.config["LIMITE_LOGIN_POR_MINUTO"] = 1000
    app.config["LIMITE_API_POR_MINUTO"] = 1000
    app.config["CORS_ORIGINS"] = frozenset()
    app.config["TRUST_FORWARDED_HEADERS"] = False
    app.extensions["limitador"] = LimitadorJanelaFixa()
    app.extensions["monitor_saude"] = MonitorSaude(SERVICOS)
    app.extensions.pop("cliente_http", None)

    yield falsos

    cliente = app.extensions.pop("cliente_http", None)
    if cliente is not None:
        await cliente.aclose()
    app.config.pop("HTTP_TRANSPORT", None)


@pytest.fixture
def client(app, servicos):
    return app.test_client()
