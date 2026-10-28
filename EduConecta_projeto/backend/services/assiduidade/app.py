"""Ponto de entrada do serviço assiduidade: cria a app Flask, regista os
blueprints e aplica os hooks globais de autenticação/permissão e cache.

Fica aqui (e não em models/controllers) porque é transversal aos dois
blueprints de negócio e precisa de correr antes de qualquer rota — à
semelhança do `before_request` partilhado do serviço `escolar`.
"""

from bson import ObjectId
from flask import Flask, g, request
from werkzeug.exceptions import RequestEntityTooLarge

from controllers.assiduidade_controller import bp as assiduidade_bp
from controllers.docs_controller import bp as docs_bp
from controllers.health_controller import bp as health_bp
from utils.http_client import consultar, erro

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

app.register_blueprint(health_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(assiduidade_bp)

# Endpoints públicos (sem sessão): health/ready para o Docker healthcheck,
# e a documentação OpenAPI/Swagger UI.
ENDPOINTS_PUBLICOS = {"health.health", "health.ready", "docs.openapi_yaml", "docs.docs"}


@app.before_request
def autenticar():
    """Exige sessão válida (via `auth`) e perfil autorizado em todas as
    rotas, exceto `/health` e `/ready`.

    As permissões são mapeadas por nome de endpoint (já com o prefixo do
    blueprint, ex. "assiduidade.marcar"): docente/educadora podem consultar
    e marcar assiduidade de turma, só o encarregado pode consultar o
    histórico de um educando. Guarda `g.conta_id` para os controllers
    saberem quem fez a marcação (`atualizado_por`).
    """
    if request.endpoint is None or request.endpoint in ENDPOINTS_PUBLICOS:
        return None
    h = request.headers.get("Authorization", "")
    partes = h.split()
    if len(h) > 8192 or len(partes) != 2 or partes[0].lower() != "bearer":
        return erro("authentication_required", "É necessário iniciar sessão.", 401)
    conta, falha = consultar("http://auth:8000/me")
    if falha is not None:
        return falha
    if (conta.get("estado") != "ativo" or not isinstance(conta.get("id"), str)
            or not ObjectId.is_valid(conta["id"])):
        return erro("invalid_session", "Sessão inválida.", 401)
    permissoes = {
        "assiduidade.consultar_turma": {"docente", "educadora"},
        "assiduidade.marcar": {"docente", "educadora"},
        "assiduidade.consultar_educando": {"encarregado"},
    }
    if conta.get("perfil") not in permissoes.get(request.endpoint, set()):
        return erro("forbidden", "O teu perfil não pode realizar esta operação.", 403)
    g.conta_id = str(ObjectId(conta["id"]))


@app.after_request
def sem_cache(resposta):
    """Dados de assiduidade são sensíveis — nunca devem ficar em cache do cliente/proxy."""
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


@app.errorhandler(RequestEntityTooLarge)
def pedido_grande(_exc):
    """Converte o erro interno do Werkzeug (corpo > MAX_CONTENT_LENGTH) no
    formato de erro padrão deste serviço."""
    return erro("request_too_large", "Pedido demasiado grande.", 413)
