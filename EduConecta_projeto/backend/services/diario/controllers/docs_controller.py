"""Controller: documentação OpenAPI/Swagger deste serviço.

Serve o ficheiro `openapi.yaml` (estático, escrito à mão a partir das rotas
reais) e uma página com Swagger UI a lê-lo. Fica num blueprint próprio
("docs"), fora do blueprint "diario", para não passar pela verificação de
acesso de `utils/acesso.py` — tal como /health e /ready, estas rotas têm de
responder sem token.
"""

import os

from flask import Blueprint, Response

bp = Blueprint("docs", __name__)

_OPENAPI_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "openapi.yaml")

_SWAGGER_UI_VERSION = "5.17.14"

_DOCS_HTML = f"""<!doctype html>
<html>
<head>
  <title>EduConecta &middot; diario &middot; API docs</title>
  <meta charset="utf-8">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{_SWAGGER_UI_VERSION}/swagger-ui.min.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{_SWAGGER_UI_VERSION}/swagger-ui-bundle.min.js"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      url: "/openapi.yaml",
      dom_id: "#swagger-ui",
    }});
  </script>
</body>
</html>
"""


@bp.get("/openapi.yaml")
def openapi_spec():
    """Devolve o ficheiro openapi.yaml em bruto, sem autenticação."""
    with open(_OPENAPI_PATH, "r", encoding="utf-8") as ficheiro:
        conteudo = ficheiro.read()

    return Response(conteudo, mimetype="application/yaml")


@bp.get("/docs")
def docs():
    """Página de documentação interativa (Swagger UI), sem autenticação."""
    return Response(_DOCS_HTML, mimetype="text/html")
