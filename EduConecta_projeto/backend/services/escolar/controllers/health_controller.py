"""Controller: endpoints de monitorização (/health, /ready).

Fica num blueprint próprio ("health"), separado do blueprint "escolar", para
não passar pelo `verificar_acesso_escolar` em controllers/blueprint.py —
estas rotas têm de responder mesmo sem token, para o Docker healthcheck
funcionar.
"""

from flask import Blueprint, jsonify
from pymongo.errors import PyMongoError

from db import database

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    """Liveness check — responde sempre 200 se o processo estiver a correr."""
    return jsonify({
        "status": "ok",
        "service": "escolar",
        "application": "EduConecta",
    }), 200


@bp.get("/ready")
def ready():
    """Readiness check — 200 só se a ligação à Atlas estiver mesmo a funcionar."""
    try:
        database.list_collection_names()
    except PyMongoError:
        return jsonify({
            "status": "not_ready",
            "service": "escolar",
            "database": "unavailable",
        }), 503

    return jsonify({
        "status": "ready",
        "service": "escolar",
        "database": "connected",
    }), 200
