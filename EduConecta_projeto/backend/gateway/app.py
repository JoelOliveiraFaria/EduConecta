"""Ponto de entrada do gateway — cria a app e regista os controllers.

Único ponto de entrada da API (/api/...): valida o token JWT, limita pedidos
e encaminha cada um para o serviço responsável. Não tem lógica de negócio.
"""

import logging
import os
import re
import secrets
import time

from quart import Quart, g, request
from werkzeug.exceptions import RequestEntityTooLarge

from controllers.gateway_controller import bp as gateway_bp
from controllers.proxy_controller import bp as proxy_bp
from rotas import MAX_CORPO_GLOBAL, SERVICOS
from utils.cliente import fechar_cliente, obter_cliente
from utils.limite import LimitadorJanelaFixa
from utils.respostas import erro
from utils.saude import MonitorSaude

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# O httpx regista cada pedido aos serviços; o gateway já regista os seus.
logging.getLogger("httpx").setLevel(logging.WARNING)


def _booleano(nome, padrao):
    return os.environ.get(nome, str(padrao)).strip().lower() in {"1", "true", "sim", "yes"}


# O segredo é o mesmo do serviço auth, que assina os tokens. Falha cedo, como o auth.
jwt_secret = os.environ["JWT_SECRET_KEY"]
if len(jwt_secret) < 32:
    raise RuntimeError("A chave JWT deve ter pelo menos 32 caracteres.")

app = Quart(__name__)
app.json.ensure_ascii = False
# Teto global; o limite de cada rota é aplicado depois, em proxy_controller.
app.config["MAX_CONTENT_LENGTH"] = MAX_CORPO_GLOBAL + 1024 * 1024

app.config.update(
    JWT_SECRET_KEY=jwt_secret,
    UPSTREAMS={
        servico: os.environ.get(f"UPSTREAM_{servico.upper()}", f"http://{servico}:8000")
        for servico in SERVICOS
    },
    # Origens autorizadas a chamar a API a partir de um browser. Vazio = nenhuma
    # (em produção o CloudFront serve a app e /api na mesma origem).
    CORS_ORIGINS=frozenset(
        origem.strip() for origem in os.environ.get("CORS_ORIGINS", "").split(",") if origem.strip()
    ),
    # Só ativar quando o gateway é alcançável unicamente pelo proxy de confiança.
    TRUST_FORWARDED_HEADERS=_booleano("TRUST_FORWARDED_HEADERS", False),
    LIMITE_LOGIN_POR_MINUTO=int(os.environ.get("RATE_LIMIT_LOGIN_PER_MINUTE", "5")),
    LIMITE_API_POR_MINUTO=int(os.environ.get("RATE_LIMIT_API_PER_MINUTE", "300")),
    ACTIVE_HEALTH_CHECKS=_booleano("ACTIVE_HEALTH_CHECKS", True),
)

app.extensions["limitador"] = LimitadorJanelaFixa()
app.extensions["monitor_saude"] = MonitorSaude(SERVICOS)

app.register_blueprint(gateway_bp)
app.register_blueprint(proxy_bp)

_ID_VALIDO = re.compile(r"[A-Za-z0-9._-]{1,64}")


@app.before_serving
async def arrancar_verificacao_de_saude():
    if app.config["ACTIVE_HEALTH_CHECKS"]:
        app.add_background_task(
            app.extensions["monitor_saude"].correr,
            lambda: obter_cliente(app),
            app.config["UPSTREAMS"],
        )


@app.after_serving
async def fechar_ligacoes():
    await fechar_cliente(app)


@app.before_request
async def iniciar_pedido():
    g.inicio = time.perf_counter()
    recebido = request.headers.get("X-Request-Id", "")
    g.pedido_id = recebido if _ID_VALIDO.fullmatch(recebido) else secrets.token_hex(16)


@app.after_request
async def concluir_pedido(resposta):
    pedido_id = getattr(g, "pedido_id", "-")
    resposta.headers["X-Request-Id"] = pedido_id

    # CORS só nas rotas que existem; a resposta ao pedido prévio já tem os seus cabeçalhos.
    origem = request.headers.get("Origin")
    if getattr(g, "rota", None) is not None and origem in app.config["CORS_ORIGINS"]:
        resposta.headers["Access-Control-Allow-Origin"] = origem
        resposta.headers["Access-Control-Expose-Headers"] = "X-Request-Id"
        resposta.headers["Vary"] = "Origin"

    duracao = (time.perf_counter() - getattr(g, "inicio", time.perf_counter())) * 1000
    app.logger.info(
        "%s %s -> %s em %.0f ms (pedido %s)",
        request.method, request.path, resposta.status_code, duracao, pedido_id,
    )
    return resposta


@app.errorhandler(RequestEntityTooLarge)
async def corpo_demasiado_grande(_):
    return erro("payload_too_large", "O pedido é demasiado grande.", 413)
