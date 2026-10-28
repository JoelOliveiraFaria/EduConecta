from flask import Blueprint, jsonify
from pymongo.errors import PyMongoError

from db import database
from utils.service_client import erro

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "comunicados",
        "application": "EduConecta",
    }), 200


@bp.get("/ready")
def ready():
    try:
        database.list_collection_names()

    except PyMongoError:
        return erro(
            "database_unavailable",
            "A base de dados dos Comunicados não está disponível.",
            503,
        )

    return jsonify({
        "status": "ready",
        "service": "comunicados",
        "database": "connected",
    }), 200
