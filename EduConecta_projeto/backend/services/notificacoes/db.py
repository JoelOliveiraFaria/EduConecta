"""Ligação ao MongoDB Atlas (base de dados deste serviço).

Expõe `notificacoes` (notificações in-app por utilizador) e `auditoria`
(registo de eventos processados que não geram notificação para ninguém,
ex: aluno.eliminado — só para prova de que o consumidor RabbitMQ os
recebeu e processou). Não contém lógica de negócio.
"""

import os

from pymongo import MongoClient

database_name = os.environ["MONGO_NOTIFICACOES_DATABASE"]

client = MongoClient(
    os.environ["MONGO_URI"],
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
)

database = client[database_name]
notificacoes = database["notificacoes"]
auditoria = database["auditoria"]
