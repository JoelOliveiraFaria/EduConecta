"""Ligação ao MongoDB Atlas (base de dados diario_db) e constantes partilhadas.

Expõe `database`/`registos` para os models consumirem, e os endereços internos
dos outros serviços usados por utils/acesso.py para validar acesso.
"""

import os

from pymongo import MongoClient

database_name = os.environ["MONGO_DIARIO_DATABASE"]

client = MongoClient(
    os.environ["MONGO_URI"],
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
)

database = client[database_name]
registos = database["registos"]

# Endereços internos (rede Docker) dos serviços consultados para validar
# sessão e permissões — este serviço nunca decide sozinho quem pode o quê.
AUTH_URL = "http://auth:8000"
SCHOOL_URL = "http://escolar:8000"

# Campos de texto livre que compõem um registo diário; usados tanto na
# validação de input como na serialização da resposta.
CAMPOS_TEXTO = (
    "alimentacao",
    "sono",
    "higiene",
    "atividades",
    "observacoes",
)
