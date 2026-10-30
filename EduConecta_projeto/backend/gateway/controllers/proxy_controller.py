"""Controller: encaminha os pedidos /api/... para o serviço responsável.

Ordem das verificações (a primeira que falhar responde, sem tocar no serviço):
  1. o caminho é "limpo" e existe na tabela de rotas (senão 404);
  2. pedido de verificação prévia de CORS (responde sem autenticar);
  3. token JWT válido, exceto nas rotas públicas (senão 401);
  4. limite de pedidos (senão 429);
  5. o serviço está de pé (senão 503);
  6. o corpo cabe no limite da rota (senão 413);
  7. encaminha, devolvendo a resposta do serviço tal como veio.
"""

import httpx
from quart import Blueprint, Response, current_app, g, request
from werkzeug.datastructures import Headers
from werkzeug.exceptions import RequestEntityTooLarge

from rotas import PREFIXO, corresponder
from utils.caminhos import caminho_seguro
from utils.cliente import obter_cliente
from utils.respostas import erro
from utils.tokens import autenticar

bp = Blueprint("proxy", __name__)

METODOS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]

# Cabeçalhos que só valem para uma ligação e nunca se reencaminham (RFC 9110).
_POR_LIGACAO = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "trailers", "transfer-encoding", "upgrade",
}
# Cabeçalhos que o gateway define ele próprio; os que o cliente enviar são descartados.
# X-Internal-Key só existe entre serviços e nunca pode entrar pela porta do gateway.
_DO_GATEWAY = {
    "host", "content-length", "x-internal-key", "x-request-id",
    "x-forwarded-for", "x-forwarded-proto", "x-forwarded-host", "forwarded",
}

_TIMEOUT_LIGACAO = 5.0
_TIMEOUT_COMUNICADOS = 120.0  # uploads de vídeo e fotografia
_TIMEOUT_PADRAO = 30.0


@bp.route("/", defaults={"caminho": ""}, methods=METODOS)
@bp.route("/<path:caminho>", methods=METODOS)
async def encaminhar(caminho):
    bruto = _caminho_bruto()

    if not caminho_seguro(bruto, request.path):
        return erro("not_found", "Recurso não encontrado.", 404)

    rota = corresponder(request.path)
    if rota is None:
        return erro("not_found", "Recurso não encontrado.", 404)
    g.rota = rota

    if _e_pedido_previo_cors():
        return _responder_pedido_previo_cors()

    claims = None
    if not rota.publica:
        claims, falha = autenticar(
            request.headers.get("Authorization", ""), current_app.config["JWT_SECRET_KEY"]
        )
        if falha is not None:
            return erro(falha[0], falha[1], 401)

    permitido, espera = _aplicar_limite(rota, claims)
    if not permitido:
        return erro(
            "too_many_requests", "Demasiados pedidos. Tenta novamente daqui a pouco.", 429,
            {"Retry-After": str(max(1, round(espera)))},
        )

    if not current_app.extensions["monitor_saude"].saudavel(rota.servico):
        return erro("dependency_unavailable", "Serviço indisponível.", 503)

    corpo, recusa = await _ler_corpo(rota)
    if recusa is not None:
        return recusa

    return await _reencaminhar(rota, bruto, corpo)


def _caminho_bruto():
    """Caminho tal como o cliente o enviou (ainda codificado), sem a query string."""
    bruto = request.scope.get("raw_path")
    if bruto:
        return bruto.decode("ascii", errors="replace").split("?", 1)[0]
    return request.path


def _ip_cliente():
    """IP do cliente. Atrás de um proxy de confiança (CloudFront, Ingress) é o
    último endereço de X-Forwarded-For, o que esse proxy acrescentou."""
    if current_app.config["TRUST_FORWARDED_HEADERS"]:
        encaminhados = request.headers.get("X-Forwarded-For", "")
        if encaminhados.strip():
            return encaminhados.split(",")[-1].strip()
    return request.remote_addr or "desconhecido"


def _aplicar_limite(rota, claims):
    """Login: por IP. Resto da API: por utilizador (ou por IP nas rotas públicas)."""
    if rota.limite == "login":
        chave = f"login:{_ip_cliente()}"
        maximo = current_app.config["LIMITE_LOGIN_POR_MINUTO"]
    else:
        chave = f"api:{claims['sub'] if claims else _ip_cliente()}"
        maximo = current_app.config["LIMITE_API_POR_MINUTO"]
    return current_app.extensions["limitador"].tentar(chave, maximo)


def _e_pedido_previo_cors():
    return (request.method == "OPTIONS"
            and "Origin" in request.headers
            and "Access-Control-Request-Method" in request.headers)


def _responder_pedido_previo_cors():
    """Sem origens configuradas (ou com uma origem desconhecida) a resposta
    não autoriza nada, por isso o browser bloqueia o pedido."""
    resposta = Response(b"", status=204)
    origem = request.headers["Origin"]
    if origem in current_app.config["CORS_ORIGINS"]:
        resposta.headers["Access-Control-Allow-Origin"] = origem
        resposta.headers["Access-Control-Allow-Methods"] = request.headers["Access-Control-Request-Method"]
        pedidos = request.headers.get("Access-Control-Request-Headers")
        if pedidos:
            resposta.headers["Access-Control-Allow-Headers"] = pedidos
        resposta.headers["Access-Control-Max-Age"] = "600"
    resposta.headers["Vary"] = "Origin"
    return resposta


async def _ler_corpo(rota):
    """Lê o corpo do pedido, recusando-o se passar do limite da rota."""
    demasiado_grande = erro("payload_too_large", "O pedido é demasiado grande.", 413)

    declarado = request.content_length
    if declarado is not None and declarado > rota.max_corpo:
        return None, demasiado_grande

    try:
        corpo = await request.get_data()
    except RequestEntityTooLarge:
        return None, demasiado_grande

    if len(corpo) > rota.max_corpo:
        return None, demasiado_grande
    return corpo, None


def _cabecalhos_para_servico():
    """Cabeçalhos do pedido sem os que não se reencaminham, mais os do gateway."""
    descartar = _POR_LIGACAO | _DO_GATEWAY
    for nome in request.headers.get("Connection", "").split(","):
        descartar = descartar | {nome.strip().lower()}

    cabecalhos = [(nome, valor) for nome, valor in request.headers.items() if nome.lower() not in descartar]

    anteriores = request.headers.get("X-Forwarded-For", "") if current_app.config["TRUST_FORWARDED_HEADERS"] else ""
    cabecalhos.append(("X-Forwarded-For", f"{anteriores}, {request.remote_addr}" if anteriores else str(request.remote_addr)))
    cabecalhos.append(("X-Forwarded-Proto", request.scheme))
    cabecalhos.append(("X-Forwarded-Host", request.host))
    cabecalhos.append(("X-Request-Id", g.pedido_id))
    return cabecalhos


async def _reencaminhar(rota, bruto, corpo):
    base = current_app.config["UPSTREAMS"][rota.servico]
    caminho_servico = rota.caminho_servico or bruto[len(PREFIXO):]
    consulta = request.query_string.decode("latin-1")
    url = f"{base}{caminho_servico}" + (f"?{consulta}" if consulta else "")

    tempo = _TIMEOUT_COMUNICADOS if rota.servico == "comunicados" else _TIMEOUT_PADRAO
    cliente = obter_cliente(current_app)
    pedido = cliente.build_request(
        request.method, url,
        headers=_cabecalhos_para_servico(),
        content=corpo or None,
        timeout=httpx.Timeout(tempo, connect=_TIMEOUT_LIGACAO),
    )

    try:
        resposta = await cliente.send(pedido, stream=True)
    except httpx.TimeoutException:
        current_app.logger.warning("Timeout a contactar %s (%s).", rota.servico, url)
        return erro("dependency_timeout", "O serviço demorou demasiado a responder.", 504)
    except httpx.HTTPError as exc:
        current_app.logger.warning("Falha a contactar %s: %s", rota.servico, exc)
        return erro("dependency_unavailable", "Serviço indisponível.", 502)

    cabecalhos = Headers()
    for nome, valor in resposta.headers.multi_items():
        if nome.lower() not in _POR_LIGACAO:
            cabecalhos.add(nome, valor)

    async def corpo_da_resposta():
        # aiter_raw: os bytes seguem exatamente como o serviço os enviou,
        # por isso o Content-Length e o Content-Encoding continuam certos.
        try:
            async for bloco in resposta.aiter_raw():
                yield bloco
        finally:
            await resposta.aclose()

    return Response(corpo_da_resposta(), status=resposta.status_code, headers=cabecalhos)
