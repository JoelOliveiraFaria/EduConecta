import jwt
import pytest

from conftest import SEGREDO, fazer_token

ROTA = "/api/me/notificacoes"


async def _assert_recusado(client, servicos, cabecalhos, erro):
    resposta = await client.get(ROTA, headers=cabecalhos)

    assert resposta.status_code == 401
    assert resposta.headers["WWW-Authenticate"] == "Bearer"
    assert (await resposta.get_json())["error"] == erro
    # Recusado no gateway: o serviço nunca chega a ser contactado.
    assert servicos.pedidos == []


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


async def test_sem_token_e_recusado(client, servicos):
    await _assert_recusado(client, servicos, {}, "authentication_required")


async def test_esquema_que_nao_e_bearer_e_recusado(client, servicos):
    await _assert_recusado(client, servicos, {"Authorization": "Basic dXRpbDpwYXNz"}, "authentication_required")


async def test_bearer_sem_token_e_recusado(client, servicos):
    await _assert_recusado(client, servicos, {"Authorization": "Bearer"}, "authentication_required")


async def test_token_expirado_e_recusado(client, servicos):
    await _assert_recusado(client, servicos, _bearer(fazer_token(validade=-30)), "token_expired")


@pytest.mark.parametrize("estrago", [
    {"audiencia": "outra-api"},
    {"emissor": "outro-emissor"},
    {"segredo": "um-segredo-diferente-com-mais-de-32-caracteres"},
    {"jti": False},
    {"sub": None},
    {"iat": False},
    {"algoritmo": "HS512"},
], ids=["audiencia", "emissor", "segredo", "sem-jti", "sem-sub", "sem-iat", "algoritmo-diferente"])
async def test_token_invalido_e_recusado(client, servicos, estrago):
    await _assert_recusado(client, servicos, _bearer(fazer_token(**estrago)), "invalid_token")


async def test_token_sem_assinatura_alg_none_e_recusado(client, servicos):
    sem_assinatura = jwt.encode(
        {"sub": "x", "iss": "educonecta-auth", "aud": "educonecta-api", "iat": 1, "exp": 9999999999, "jti": "j"},
        key=None, algorithm="none",
    )
    await _assert_recusado(client, servicos, _bearer(sem_assinatura), "invalid_token")


async def test_lixo_no_lugar_do_token_e_recusado(client, servicos):
    await _assert_recusado(client, servicos, _bearer("isto.nao.e-um-jwt"), "invalid_token")


async def test_cabecalho_gigante_e_recusado(client, servicos):
    await _assert_recusado(client, servicos, _bearer("a" * 9000), "authentication_required")


async def test_token_valido_passa_e_o_token_segue_para_o_servico(client, servicos):
    token = fazer_token()

    resposta = await client.get(ROTA, headers=_bearer(token))

    assert resposta.status_code == 200
    # Os serviços continuam a validar a conta no /me, por isso precisam do token.
    assert servicos.cabecalho_recebido("Authorization") == f"Bearer {token}"


async def test_login_e_publico(client, servicos):
    resposta = await client.post("/api/login", data=b"{}")

    assert resposta.status_code == 200
    assert servicos.ultimo.url.host == "auth"


async def test_documentacao_e_publica(client, servicos):
    resposta = await client.get("/api/openapi/escolar.yaml")

    assert resposta.status_code == 200
    assert servicos.ultimo.url.path == "/openapi.yaml"


async def test_o_segredo_do_gateway_e_o_configurado(app):
    assert app.config["JWT_SECRET_KEY"] == SEGREDO
