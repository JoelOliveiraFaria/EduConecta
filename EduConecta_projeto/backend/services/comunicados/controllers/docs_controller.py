"""Controller: documentação interativa da API (OpenAPI + Swagger UI).

Fica num blueprint próprio, à parte dos blueprints de negócio, e por isso
nunca passa pelas verificações de autorização de utils/acesso.py — tal como
/health e /ready, a documentação tem de ser legível sem sessão.
"""

import os

from flask import Blueprint, Response

bp = Blueprint("docs", __name__)

_CAMINHO_SPEC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "openapi.yaml")

_PAGINA_SWAGGER = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>EduConecta — comunicados · docs</title>
  <link rel="stylesheet"
    href="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui.min.css">
  <style>body { margin: 0; }</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/swagger-ui/5.17.14/swagger-ui-bundle.min.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: "/openapi.yaml",
        dom_id: "#swagger-ui",
        presets: [SwaggerUIBundle.presets.apis],
      });
    };
  </script>
</body>
</html>
"""


@bp.get("/openapi.yaml")
def especificacao():
    """Serve o ficheiro openapi.yaml em disco, tal como está (sem autenticação)."""
    with open(_CAMINHO_SPEC, "r", encoding="utf-8") as ficheiro:
        conteudo = ficheiro.read()

    return Response(conteudo, mimetype="application/yaml")


@bp.get("/docs")
def documentacao():
    """Página HTML com o Swagger UI, a consumir /openapi.yaml (sem autenticação)."""
    return Response(_PAGINA_SWAGGER, mimetype="text/html")
