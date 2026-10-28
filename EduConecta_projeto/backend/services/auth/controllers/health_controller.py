from quart import Blueprint, jsonify
from pymongo.errors import PyMongoError

import models.utilizador as modelo_utilizador

bp = Blueprint("health", __name__)


@bp.get("/health")
async def health():
    return jsonify({
        "status": "ok",
        "service": "auth",
        "application": "EduConecta",
    }), 200


@bp.get("/ready")
async def ready():
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
