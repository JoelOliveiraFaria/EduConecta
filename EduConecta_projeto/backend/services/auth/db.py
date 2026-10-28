import os

from pymongo import AsyncMongoClient

database_name = os.environ["MONGO_AUTH_DATABASE"]

client = AsyncMongoClient(
    os.environ["MONGO_URI"],
    tz_aware=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
)

database = client[database_name]
utilizadores = database["utilizadores"]
