"""Limite de pedidos, CORS e identificação dos pedidos."""

import re

from conftest import fazer_token
from utils.limite import LimitadorJanelaFixa


def test_limitador_bloqueia_ao_passar_do_maximo_e_liberta_na_janela_seguinte():
    agora = [0.0]
    limitador = LimitadorJanelaFixa(relogio=lambda: agora[0])

    assert [limitador.tentar("k", 3)[0] for _ in range(3)] == [True, True, True]
    permitido, espera = limitador.tentar("k", 3)
    assert not permitido
    assert 0 < espera <= 60

    agora[0] = 61.0
    assert limitador.tentar("k", 3)[0]


def test_limitador_conta_cada_chave_em_separado():
    limitador = LimitadorJanelaFixa(relogio=lambda: 0.0)

    assert limitador.tentar("a", 1)[0]
    assert not limitador.tentar("a", 1)[0]
    assert limitador.tentar("b", 1)[0]


def test_limitador_descarta_janelas_terminadas(monkeypatch):
    agora = [0.0]
    limitador = LimitadorJanelaFixa(relogio=lambda: agora[0])
    monkeypatch.setattr("utils.limite._MAX_CHAVES", 5)

    for i in range(6):
        limitador.tentar(f"k{i}", 1)
    agora[0] = 120.0
    limitador.tentar("nova", 1)
    for i in range(6):
        limitador.tentar(f"x{i}", 1)

    assert "k0" not in limitador._janelas


async def test_login_e_limitado_a_5_tentativas_por_minuto(app, client, servicos):
    app.config["LIMITE_LOGIN_POR_MINUTO"] = 5

    for _ in range(5):
        assert (await client.post("/api/login", data=b"{}")).status_code == 200

    bloqueado = await client.post("/api/login", data=b"{}")

    assert bloqueado.status_code == 429
    assert int(bloqueado.headers["Retry-After"]) >= 1
    assert (await bloqueado.get_json())["error"] == "too_many_requests"
    assert len(servicos.pedidos) == 5


async def test_o_limite_do_login_nao_afeta_o_resto_da_api(app, client, servicos, cabecalhos_auth):
    app.config["LIMITE_LOGIN_POR_MINUTO"] = 1
    await client.post("/api/login", data=b"{}")
    assert (await client.post("/api/login", data=b"{}")).status_code == 429

    for _ in range(10):
        assert (await client.get("/api/me", headers=cabecalhos_auth)).status_code == 200


async def test_limite_da_api_e_por_utilizador(app, client, servicos):
    app.config["LIMITE_API_POR_MINUTO"] = 2
    ana = {"Authorization": f"Bearer {fazer_token(sub='aaaaaaaaaaaaaaaaaaaaaaaa')}"}
    rui = {"Authorization": f"Bearer {fazer_token(sub='bbbbbbbbbbbbbbbbbbbbbbbb')}"}

    assert (await client.get("/api/me", headers=ana)).status_code == 200
    assert (await client.get("/api/me", headers=ana)).status_code == 200
    assert (await client.get("/api/me", headers=ana)).status_code == 429

    assert (await client.get("/api/me", headers=rui)).status_code == 200


async def test_pedidos_recusados_por_autenticacao_nao_gastam_o_limite_de_ninguem(app, client, servicos):
    app.config["LIMITE_API_POR_MINUTO"] = 1

    for _ in range(5):
        assert (await client.get("/api/me")).status_code == 401


async def test_atras_de_um_proxy_de_confianca_o_limite_usa_o_ip_real(app, client, servicos):
    app.config["LIMITE_LOGIN_POR_MINUTO"] = 1
    app.config["TRUST_FORWARDED_HEADERS"] = True

    # O proxy de confiança acrescenta no fim o IP que viu; o que vem antes pode ser forjado pelo cliente.
    um = {"X-Forwarded-For": "9.9.9.9, 1.1.1.1"}
    outro = {"X-Forwarded-For": "9.9.9.9, 2.2.2.2"}
    forjado = {"X-Forwarded-For": "7.7.7.7, 1.1.1.1"}

    assert (await client.post("/api/login", data=b"{}", headers=um)).status_code == 200
    assert (await client.post("/api/login", data=b"{}", headers=um)).status_code == 429
    # Mudar o prefixo forjado não foge ao limite; mudar o IP real, sim.
    assert (await client.post("/api/login", data=b"{}", headers=forjado)).status_code == 429
    assert (await client.post("/api/login", data=b"{}", headers=outro)).status_code == 200


async def test_sem_proxy_de_confianca_o_x_forwarded_for_do_cliente_e_ignorado(app, client, servicos):
    """Se não for ignorado, bastava mudar o cabeçalho a cada tentativa para fugir ao limite."""
    app.config["LIMITE_LOGIN_POR_MINUTO"] = 1

    assert (await client.post("/api/login", data=b"{}", headers={"X-Forwarded-For": "1.1.1.1"})).status_code == 200
    assert (await client.post("/api/login", data=b"{}", headers={"X-Forwarded-For": "2.2.2.2"})).status_code == 429


# --- CORS ---

PEDIDO_PREVIO = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
                 "Access-Control-Request-Headers": "authorization"}


async def test_cors_sem_origens_configuradas_nao_autoriza_ninguem(client, servicos):
    resposta = await client.options("/api/me", headers=PEDIDO_PREVIO)

    assert resposta.status_code == 204
    assert "Access-Control-Allow-Origin" not in resposta.headers


async def test_cors_autoriza_a_origem_configurada(app, client, servicos):
    app.config["CORS_ORIGINS"] = frozenset({"http://localhost:5173"})

    resposta = await client.options("/api/me", headers=PEDIDO_PREVIO)

    assert resposta.status_code == 204
    assert resposta.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert resposta.headers["Access-Control-Allow-Methods"] == "GET"
    assert resposta.headers["Access-Control-Allow-Headers"] == "authorization"
    # O pedido prévio não leva token e não chega ao serviço.
    assert servicos.pedidos == []


async def test_cors_recusa_outra_origem(app, client, servicos):
    app.config["CORS_ORIGINS"] = frozenset({"http://localhost:5173"})

    resposta = await client.options("/api/me", headers={**PEDIDO_PREVIO, "Origin": "http://evil.example"})

    assert resposta.status_code == 204
    assert "Access-Control-Allow-Origin" not in resposta.headers


async def test_cors_acrescenta_a_origem_as_respostas_normais(app, client, servicos, cabecalhos_auth):
    app.config["CORS_ORIGINS"] = frozenset({"http://localhost:5173"})

    resposta = await client.get("/api/me", headers={**cabecalhos_auth, "Origin": "http://localhost:5173"})

    assert resposta.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert resposta.headers["Access-Control-Expose-Headers"] == "X-Request-Id"


async def test_cors_nao_acrescenta_nada_a_outra_origem(app, client, servicos, cabecalhos_auth):
    app.config["CORS_ORIGINS"] = frozenset({"http://localhost:5173"})

    resposta = await client.get("/api/me", headers={**cabecalhos_auth, "Origin": "http://evil.example"})

    assert "Access-Control-Allow-Origin" not in resposta.headers


async def test_cors_nao_existe_para_rotas_que_nao_existem(app, client, servicos):
    app.config["CORS_ORIGINS"] = frozenset({"http://localhost:5173"})

    resposta = await client.options("/api/desconhecido", headers=PEDIDO_PREVIO)

    assert resposta.status_code == 404
    assert "Access-Control-Allow-Origin" not in resposta.headers


# --- X-Request-Id ---

async def test_gera_um_x_request_id_quando_o_cliente_nao_envia(client):
    resposta = await client.get("/health")

    assert re.fullmatch(r"[0-9a-f]{32}", resposta.headers["X-Request-Id"])


async def test_mantem_o_x_request_id_do_cliente_se_for_valido(client):
    resposta = await client.get("/health", headers={"X-Request-Id": "pedido-123"})

    assert resposta.headers["X-Request-Id"] == "pedido-123"


async def test_substitui_um_x_request_id_invalido(client):
    resposta = await client.get("/health", headers={"X-Request-Id": "tem espaços <e> símbolos"})

    assert re.fullmatch(r"[0-9a-f]{32}", resposta.headers["X-Request-Id"])
