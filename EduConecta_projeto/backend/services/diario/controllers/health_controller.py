from flask import Blueprint, jsonify
from pymongo.errors import PyMongoError

import models.registo as modelo_registo
from utils.acesso import erro

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "diario",
        "application": "EduConecta",
    }), 200


@bp.get("/ready")
def ready():
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
