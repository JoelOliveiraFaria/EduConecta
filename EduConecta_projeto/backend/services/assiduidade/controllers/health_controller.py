from flask import Blueprint, jsonify
from pymongo.errors import PyMongoError

from db import database
from utils.http_client import erro

bp = Blueprint("health", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "assiduidade"}), 200


@bp.get("/ready")
def ready():
    try:
        database.list_collection_names()
    except PyMongoError:
        return erro("database_unavailable", "Base de dados indisponível.", 503)
    return jsonify({"status": "ready", "service": "assiduidade", "database": "connected"}), 200
