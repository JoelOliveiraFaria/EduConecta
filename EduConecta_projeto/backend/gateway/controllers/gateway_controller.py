"""Controller: endpoints do próprio gateway — estado, e documentação da API.

Todos são públicos. Não encaminham nada: respondem o gateway.
"""

import asyncio

import httpx
from quart import Blueprint, Response, current_app, jsonify

from rotas import SERVICOS
from utils.cliente import obter_cliente
from utils.respostas import erro

bp = Blueprint("gateway", __name__)

SWAGGER_UI_VERSION = "5.17.14"

_DOCS_HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>EduConecta {servico} — API docs</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{versao}/swagger-ui.min.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{versao}/swagger-ui-bundle.min.js"></script>
  <script>
    window.onload = function () {{
      SwaggerUIBundle({{
        url: "/api/openapi/{servico}.yaml",
        dom_id: "#swagger-ui",
        // As specs dos serviços declaram servers: "/", mas atrás do gateway todas as
        // rotas levam o prefixo /api: o "Try it out" tem de o acrescentar.
        requestInterceptor: function (pedido) {{
          var url = new URL(pedido.url, window.location.origin);
          if (url.origin === window.location.origin && url.pathname.indexOf("/api/") !== 0) {{
            url.pathname = "/api" + url.pathname;
            pedido.url = url.toString();
          }}
          return pedido;
        }},
      }});
    }};
  </script>
</body>
</html>
"""


@bp.get("/health")
@bp.get("/api/health")
async def health():
    """Liveness: o processo do gateway está de pé. Não depende dos serviços."""
    return jsonify({"status": "ok", "service": "gateway"}), 200


@bp.get("/api/ready")
async def ready():
    """Pergunta o /ready a cada serviço (inclui a ligação à base de dados)."""
    cliente = obter_cliente(current_app)
    upstreams = current_app.config["UPSTREAMS"]

    async def verificar(servico):
        try:
            resposta = await cliente.get(f"{upstreams[servico]}/ready", timeout=3.0)
            return servico, resposta.is_success
        except httpx.HTTPError:
            return servico, False

    resultados = dict(await asyncio.gather(*(verificar(servico) for servico in SERVICOS)))
    estados = {servico: "ready" if pronto else "unavailable" for servico, pronto in resultados.items()}
    tudo_pronto = all(resultados.values())

    return jsonify({
        "status": "ready" if tudo_pronto else "not_ready",
        "services": estados,
    }), 200 if tudo_pronto else 503


@bp.get("/api/docs")
async def indice_docs():
    ligacoes = "".join(f'<li><a href="/api/docs/{servico}">{servico}</a></li>' for servico in SERVICOS)
    html = (
        '<!doctype html><html><head><meta charset="utf-8"><title>EduConecta — API docs</title></head><body>'
        f"<h1>EduConecta — documentação da API</h1><ul>{ligacoes}</ul></body></html>"
    )
    return Response(html, mimetype="text/html")


@bp.get("/api/docs/<servico>")
async def docs_servico(servico):
    """Swagger UI de um serviço.

    As páginas dos próprios serviços pedem `/openapi.yaml` na raiz, que atrás
    do prefixo /api deixaria de existir; por isso o gateway serve a sua.
    """
    if servico not in SERVICOS:
        return erro("not_found", "Serviço desconhecido.", 404)
    return Response(_DOCS_HTML.format(servico=servico, versao=SWAGGER_UI_VERSION), mimetype="text/html")
