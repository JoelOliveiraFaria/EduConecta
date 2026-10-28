"""Controller: endpoints de monitorização (/health, /ready) — sem autenticação."""

from quart import Blueprint, jsonify
from pymongo.errors import PyMongoError

import models.utilizador as modelo_utilizador

bp = Blueprint("health", __name__)


@bp.get("/health")
async def health():
    """Liveness check — responde sempre 200 se o processo estiver a correr."""
    return jsonify({
        "status": "ok",
        "service": "auth",
        "application": "EduConecta",
    }), 200


@bp.get("/ready")
async def ready():
    """Readiness check — 200 só se a ligação à Atlas estiver mesmo a funcionar."""
    try:
        await modelo_utilizador.contar_colecoes()

    except PyMongoError:
        return jsonify({
            "status": "not_ready",
            "service": "auth",
            "database": "unavailable",
        }), 503

    return jsonify({
        "status": "ready",
        "service": "auth",
        "database": "connected",
    }), 200
