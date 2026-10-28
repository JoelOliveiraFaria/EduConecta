"""Controller: documentação OpenAPI/Swagger UI deste serviço.

Fica num blueprint próprio ("docs"), fora do blueprint "escolar", pela mesma
razão que health_controller.py — estas rotas têm de responder sem token,
para quem for consultar a documentação não precisar de autenticar-se antes.
"""

import os

from flask import Blueprint, Response

bp = Blueprint("docs", __name__)

_OPENAPI_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.yaml")

_SWAGGER_UI_VERSION = "5.17.14"

_DOCS_HTML = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>EduConecta — escolar — API docs</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{_SWAGGER_UI_VERSION}/swagger-ui.min.css">
  <style>body {{ margin: 0; }}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/{_SWAGGER_UI_VERSION}/swagger-ui-bundle.min.js"></script>
  <script>
    window.onload = function () {{
      window.ui = SwaggerUIBundle({{
        url: "/openapi.yaml",
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis],
      }});
    }};
  </script>
</body>
</html>
"""


@bp.get("/openapi.yaml")
def openapi_spec():
    """Serve o ficheiro openapi.yaml em bruto (sem autenticação)."""
    with open(_OPENAPI_PATH, "r", encoding="utf-8") as ficheiro:
        conteudo = ficheiro.read()

    return Response(conteudo, mimetype="application/yaml")


@bp.get("/docs")
def docs_ui():
    """Página de documentação interativa (Swagger UI), lendo /openapi.yaml."""
    return Response(_DOCS_HTML, mimetype="text/html")
