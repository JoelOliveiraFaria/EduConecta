from flask import Blueprint, jsonify
from pymongo.errors import PyMongoError

from db import database

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "escolar",
        "application": "EduConecta",
    }), 200


@bp.get("/ready")
def ready():
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
