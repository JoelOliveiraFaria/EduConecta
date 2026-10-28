"""Ligação ao MongoDB Atlas (base de dados comunicados_db) e os dois buckets
GridFS usados para guardar ficheiros binários (fotografias e vídeos), mais as
constantes de configuração partilhadas por models/controllers/utils deste
serviço (limites de tamanho, URLs internas dos outros serviços, perfis).
"""

import os

from gridfs import GridFS
from pymongo import MongoClient

database_name = os.environ["MONGO_COMUNICADOS_DATABASE"]

client = MongoClient(
    os.environ["MONGO_URI"],
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
)

database = client[database_name]

# GridFS guarda o binário em <collection>.files/<collection>.chunks;
# um bucket por tipo de anexo para poderem ter políticas/índices distintos.
fotografias = GridFS(database, collection="fotografias")
videos = GridFS(database, collection="videos")
buckets = {"fotografias": fotografias, "videos": videos}

MAX_FOTOGRAFIA_BYTES = 5 * 1024 * 1024
MAX_FOTOGRAFIA_PIXEIS = 20_000_000
FORMATOS_FOTOGRAFIA = {"JPEG", "PNG", "WEBP"}

MAX_VIDEO_BYTES = 25 * 1024 * 1024

# Endereços internos (rede Docker) dos outros serviços, usados por
# utils/acesso.py para validar sessão (auth) e relações turma/aluno (escolar).
AUTH_URL = "http://auth:8000"
SCHOOL_URL = "http://escolar:8000"
PERFIS_PUBLICACAO = {"docente", "educadora"}
