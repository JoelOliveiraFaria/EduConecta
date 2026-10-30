"""Endpoints do próprio gateway e verificação de saúde dos serviços."""

import httpx
import pytest

from rotas import SERVICOS
from utils.saude import MonitorSaude


async def test_health(client, servicos):
    resposta = await client.get("/health")

    assert resposta.status_code == 200
    assert (await resposta.get_json()) == {"status": "ok", "service": "gateway"}
    assert (await client.get("/api/health")).status_code == 200
    assert servicos.pedidos == []


async def test_ready_quando_todos_os_servicos_estao_prontos(client, servicos):
    resposta = await client.get("/api/ready")

    assert resposta.status_code == 200
    corpo = await resposta.get_json()
    assert corpo["status"] == "ready"
    assert corpo["services"] == {servico: "ready" for servico in SERVICOS}
    assert {pedido.url.path for pedido in servicos.pedidos} == {"/ready"}


async def test_ready_quando_um_servico_falha(client, servicos):
    servicos.respostas["diario"] = (503, {}, b'{"error":"database_unavailable"}')
    servicos.erros["comunicados"] = httpx.ConnectError("em baixo")

    resposta = await client.get("/api/ready")

    assert resposta.status_code == 503
    corpo = await resposta.get_json()
    assert corpo["status"] == "not_ready"
    assert corpo["services"]["diario"] == "unavailable"
    assert corpo["services"]["comunicados"] == "unavailable"
    assert corpo["services"]["auth"] == "ready"


async def test_documentacao_nao_exige_token(client):
    indice = await client.get("/api/docs")
    assert indice.status_code == 200

    for servico in SERVICOS:
        pagina = await client.get(f"/api/docs/{servico}")
        assert pagina.status_code == 200
        assert f"/api/openapi/{servico}.yaml" in (await pagina.get_data(as_text=True))


async def test_swagger_acrescenta_o_prefixo_api_aos_pedidos_do_try_it_out(client):
    """As specs dos serviços declaram servers "/"; sem isto o "Try it out" chamaria /login e não /api/login."""
    pagina = await (await client.get("/api/docs/auth")).get_data(as_text=True)

    assert "requestInterceptor" in pagina
    assert 'url.pathname = "/api" + url.pathname' in pagina


async def test_documentacao_de_servico_desconhecido(client):
    assert (await client.get("/api/docs/inexistente")).status_code == 404


# --- monitor de saúde ---

def _cliente(respostas):
    """Cliente cujos /health respondem conforme `respostas` (servico -> código, ou exceção)."""
    def tratar(pedido):
        resultado = respostas[pedido.url.host]
        if isinstance(resultado, Exception):
            raise resultado
        return httpx.Response(resultado)
    return httpx.AsyncClient(transport=httpx.MockTransport(tratar))


UPSTREAMS = {servico: f"http://{servico}:8000" for servico in SERVICOS}


async def test_servico_so_fica_indisponivel_apos_3_falhas_seguidas():
    monitor = MonitorSaude(SERVICOS)
    respostas = {servico: 200 for servico in SERVICOS}
    respostas["escolar"] = 500

    async with _cliente(respostas) as cliente:
        await monitor.verificar(cliente, UPSTREAMS)
        await monitor.verificar(cliente, UPSTREAMS)
        assert monitor.saudavel("escolar")

        await monitor.verificar(cliente, UPSTREAMS)
        assert not monitor.saudavel("escolar")
        assert monitor.saudavel("auth")


async def test_servico_volta_a_receber_pedidos_quando_responde():
    monitor = MonitorSaude(SERVICOS)
    respostas = {servico: 200 for servico in SERVICOS}
    respostas["escolar"] = httpx.ConnectError("em baixo")

    async with _cliente(respostas) as cliente:
        for _ in range(3):
            await monitor.verificar(cliente, UPSTREAMS)
        assert not monitor.saudavel("escolar")

        respostas["escolar"] = 200
        await monitor.verificar(cliente, UPSTREAMS)
        assert monitor.saudavel("escolar")


async def test_uma_falha_isolada_nao_conta_se_o_servico_voltar():
    monitor = MonitorSaude(SERVICOS)
    respostas = {servico: 200 for servico in SERVICOS}

    async with _cliente(respostas) as cliente:
        respostas["auth"] = 500
        await monitor.verificar(cliente, UPSTREAMS)
        await monitor.verificar(cliente, UPSTREAMS)
        respostas["auth"] = 200
        await monitor.verificar(cliente, UPSTREAMS)
        respostas["auth"] = 500
        await monitor.verificar(cliente, UPSTREAMS)
        await monitor.verificar(cliente, UPSTREAMS)

    assert monitor.saudavel("auth")


@pytest.mark.parametrize("variavel,valor", [("JWT_SECRET_KEY", "curta")])
def test_o_gateway_nao_arranca_com_um_segredo_fraco(variavel, valor, monkeypatch):
    """Mesma regra do auth: falha cedo em vez de aceitar tokens com uma chave fraca."""
    import importlib
    import sys

    monkeypatch.setenv(variavel, valor)
    antigo = sys.modules.pop("app")
    try:
        with pytest.raises(RuntimeError, match="32 caracteres"):
            importlib.import_module("app")
    finally:
        sys.modules["app"] = antigo
