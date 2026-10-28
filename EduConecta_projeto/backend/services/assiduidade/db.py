"""Ligação ao MongoDB Atlas (partilhado pelos 5 microsserviços).

Expõe `database` (a base de dados deste serviço) e `registos` (a coleção
`assiduidade`), reutilizados pelos models. Não contém lógica de negócio.
"""

import os

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
