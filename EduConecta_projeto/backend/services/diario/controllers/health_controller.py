"""Controller: endpoints de monitorização (/health, /ready) — sem autenticação."""

from flask import Blueprint, jsonify
from pymongo.errors import PyMongoError

import models.registo as modelo_registo
from utils.acesso import erro

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    """Liveness check — responde sempre 200 se o processo estiver a correr."""
    return jsonify({
        "status": "ok",
        "service": "diario",
        "application": "EduConecta",
    }), 200


@bp.get("/ready")
def ready():
    """Readiness check — só dá 200 se a ligação à Atlas estiver mesmo a funcionar."""
    try:
        modelo_registo.contar_colecoes()
    except PyMongoError:
        return erro(
            "database_unavailable",
            "A base de dados do Diário não está disponível.",
            503,
        )

    return jsonify({
        "status": "ready",
        "service": "diario",
        "database": "connected",
    }), 200
