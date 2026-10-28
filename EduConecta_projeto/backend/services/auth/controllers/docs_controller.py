"""Controller: documentação pública da API (OpenAPI + Swagger UI).

Serve o ficheiro `openapi.yaml` estático e uma página Swagger UI que o lê.
Não requer autenticação — é documentação, não um endpoint de negócio.
"""

import os

from quart import Blueprint, Response

bp = Blueprint("docs", __name__)

OPENAPI_PATH = os.path.join(os.path.dirname(__file__), "..", "openapi.yaml")

SWAGGER_UI_VERSION = "5.17.14"

DOCS_HTML = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>EduConecta auth — API docs</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{SWAGGER_UI_VERSION}/swagger-ui.min.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{SWAGGER_UI_VERSION}/swagger-ui-bundle.min.js"></script>
  <script>
    window.onload = function () {{
      SwaggerUIBundle({{
        url: "/openapi.yaml",
        dom_id: "#swagger-ui",
      }});
    }};
  </script>
</body>
</html>
"""


@bp.get("/openapi.yaml")
async def servir_spec():
    """Devolve o conteúdo bruto de openapi.yaml, sem autenticação."""
    with open(OPENAPI_PATH, "r", encoding="utf-8") as ficheiro:
        conteudo = ficheiro.read()

    return Response(conteudo, mimetype="application/yaml")


@bp.get("/docs")
async def servir_docs():
    """Página Swagger UI (via cdnjs) que lê /openapi.yaml, sem autenticação."""
    return Response(DOCS_HTML, mimetype="text/html")
