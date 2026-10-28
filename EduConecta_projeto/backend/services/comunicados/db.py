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

fotografias = GridFS(database, collection="fotografias")
videos = GridFS(database, collection="videos")
buckets = {"fotografias": fotografias, "videos": videos}

MAX_FOTOGRAFIA_BYTES = 5 * 1024 * 1024
MAX_FOTOGRAFIA_PIXEIS = 20_000_000
FORMATOS_FOTOGRAFIA = {"JPEG", "PNG", "WEBP"}

MAX_VIDEO_BYTES = 25 * 1024 * 1024

AUTH_URL = "http://auth:8000"
SCHOOL_URL = "http://escolar:8000"
PERFIS_PUBLICACAO = {"docente", "educadora"}
