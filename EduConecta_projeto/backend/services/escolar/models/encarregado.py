from bson import ObjectId
from pymongo import ReturnDocument

from db import database

colecao = database["encarregados_educacao"]


def criar(nome, telefone):
    encarregado = {"nome": nome, "telefone": telefone}
    resultado = colecao.insert_one(encarregado)
    return resultado.inserted_id, encarregado


def listar():
    return (
        colecao
        .find({}, {"nome": 1, "telefone": 1})
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter(encarregado_id):
    return colecao.find_one(
        {"_id": ObjectId(encarregado_id)},
        {"nome": 1},
    )


def obter_por_utilizador(utilizador_id):
    return colecao.find_one(
        {"utilizador_id": utilizador_id},
        {"nome": 1},
    )


def obter_com_utilizador(encarregado_id):
    return colecao.find_one(
        {"_id": ObjectId(encarregado_id)},
        {"nome": 1, "utilizador_id": 1},
    )


def associar_utilizador(encarregado_id, conta_id):
    return colecao.find_one_and_update(
        {
            "_id": ObjectId(encarregado_id),
            "$or": [
                {"utilizador_id": {"$exists": False}},
                {"utilizador_id": conta_id},
            ],
        },
        {"$set": {"utilizador_id": conta_id}},
        projection={"nome": 1, "utilizador_id": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def obter_para_chat(utilizador_id):
    return colecao.find_one(
        {"utilizador_id": utilizador_id},
        {"_id": 1},
    )


def listar_por_ids(ids):
    return (
        colecao
        .find({"_id": {"$in": ids}}, {"nome": 1, "telefone": 1})
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )
