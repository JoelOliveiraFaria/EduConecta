"""Ligação ao MongoDB Atlas (partilhado pelos 5 microsserviços).

Expõe `database` (a base de dados deste serviço), `registos` (a coleção
`assiduidade`) e `justificacoes` (a coleção de justificações de faltas,
Fase 1), reutilizados pelos models. Não contém lógica de negócio.
"""

import os

from gridfs import GridFS
from pymongo import MongoClient

database_name = os.environ["MONGO_ASSIDUIDADE_DATABASE"]

client = MongoClient(
    os.environ["MONGO_URI"],
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
)

database = client[database_name]
registos = database["assiduidade"]
justificacoes = database["justificacoes"]

# Anexo opcional de uma justificação (ex: atestado médico) — mesmo padrão
# GridFS já usado no serviço comunicados para fotografias/vídeos.
anexos_justificacao = GridFS(database, collection="anexos_justificacao")
MAX_ANEXO_BYTES = 5 * 1024 * 1024
