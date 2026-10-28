"""Ligação ao MongoDB Atlas — cliente assíncrono partilhado pelo serviço auth.

Expõe `database` e a coleção `utilizadores` para os models consumirem;
nenhum outro módulo deve construir o seu próprio MongoClient.
"""

import os

from pymongo import AsyncMongoClient

database_name = os.environ["MONGO_AUTH_DATABASE"]

# MONGO_URI aponta para o cluster partilhado na Atlas; cada serviço só
# difere na base de dados que seleciona (MONGO_AUTH_DATABASE).
client = AsyncMongoClient(
    os.environ["MONGO_URI"],
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
)

database = client[database_name]
utilizadores = database["utilizadores"]
