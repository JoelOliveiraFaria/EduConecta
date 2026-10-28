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
