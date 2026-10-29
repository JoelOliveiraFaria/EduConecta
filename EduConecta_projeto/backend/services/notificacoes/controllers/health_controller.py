"""Controller: endpoints de diagnóstico, isolados num blueprint próprio para
ficarem fora da verificação de autenticação em `app.py` (que exclui
explicitamente "health.health" e "health.ready")."""

from flask import Blueprint, jsonify
from pymongo.errors import PyMongoError

from db import database
from utils.http_client import erro

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    """Liveness check simples — não toca na base de dados."""
    return jsonify({"status": "ok", "service": "notificacoes"}), 200


@bp.get("/ready")
def ready():
    """Readiness check — confirma que a ligação à Atlas está a responder."""
    try:
        database.list_collection_names()
    except PyMongoError:
        return erro("database_unavailable", "Base de dados indisponível.", 503)
    return jsonify({"status": "ready", "service": "notificacoes", "database": "connected"}), 200
