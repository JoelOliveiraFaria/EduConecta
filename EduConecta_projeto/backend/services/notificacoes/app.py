"""Ponto de entrada do serviço notificacoes: cria a app Flask, regista os
blueprints, aplica autenticação global às rotas pessoais, e arranca o
consumidor RabbitMQ em segundo plano (Fase 2) que grava notificações a
partir dos eventos publicados pelos outros serviços (ver utils/consumidor.py).
"""

import os

from bson import ObjectId
from flask import Flask, g, request

from controllers.docs_controller import bp as docs_bp
from controllers.health_controller import bp as health_bp
from controllers.notificacao_controller import bp as notificacoes_bp
from utils.consumidor import iniciar_em_fundo
from utils.http_client import consultar, erro

app = Flask(__name__)
app.json.ensure_ascii = False

app.register_blueprint(health_bp)
app.register_blueprint(docs_bp)
app.register_blueprint(notificacoes_bp)

# Endpoints públicos (sem sessão): health/ready para o Docker healthcheck,
# e a documentação OpenAPI/Swagger UI.
ENDPOINTS_PUBLICOS = {"health.health", "health.ready", "docs.openapi_yaml", "docs.docs"}


@app.before_request
def autenticar():
    """Exige sessão válida (via `auth`) em todas as rotas, exceto /health,
    /ready, /docs e /openapi.yaml — mesmo padrão já usado nos outros
    serviços síncronos (ex: assiduidade). Qualquer perfil autenticado pode
    consultar as suas próprias notificações."""
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
    g.conta_id = str(ObjectId(conta["id"]))


@app.after_request
def sem_cache(resposta):
    """Notificações são dados pessoais — nunca devem ficar em cache do cliente/proxy."""
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


# Em testes, conftest.py define DISABLE_RABBITMQ_CONSUMER=true antes de
# importar esta app — não faz sentido ligar a um RabbitMQ real a cada corrida
# da suite de testes.
if os.environ.get("DISABLE_RABBITMQ_CONSUMER") != "true":
    iniciar_em_fundo()
