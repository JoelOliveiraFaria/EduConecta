import os

from pymongo import MongoClient

database_name = os.environ["MONGO_ESCOLAR_DATABASE"]

client = MongoClient(
    os.environ["MONGO_URI"],
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=5000,
)

database = client[database_name]
