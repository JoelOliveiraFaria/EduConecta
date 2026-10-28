"""Controller: serve a especificação OpenAPI e uma página Swagger UI para a
explorar — documentação, sem autenticação, à semelhança do /health e /ready.
"""

import os

from flask import Blueprint, Response

bp = Blueprint("docs", __name__)

_ESPECIFICACAO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "openapi.yaml")

_PAGINA_SWAGGER = """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>EduConecta - assiduidade - API docs</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.19.1/swagger-ui.min.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/4.19.1/swagger-ui-bundle.min.js"></script>
  <script>
    window.onload = function () {
      window.ui = SwaggerUIBundle({
        url: "/openapi.yaml",
        dom_id: "#swagger-ui",
      });
    };
  </script>
</body>
</html>
"""


@bp.get("/openapi.yaml")
def openapi_yaml():
    """Devolve o ficheiro openapi.yaml em bruto, lido do disco a cada pedido
    (serviço pequeno — não vale a pena cachear em memória)."""
    with open(_ESPECIFICACAO, "r", encoding="utf-8") as ficheiro:
        conteudo = ficheiro.read()
    return Response(conteudo, mimetype="application/yaml")


@bp.get("/docs")
def docs():
    """Página HTML com o Swagger UI (via cdnjs) a carregar /openapi.yaml."""
    return Response(_PAGINA_SWAGGER, mimetype="text/html")
