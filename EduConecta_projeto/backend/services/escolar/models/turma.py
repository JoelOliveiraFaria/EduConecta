from bson import ObjectId
from pymongo import ReturnDocument

from db import database

colecao = database["turmas"]


def criar(nome, ano_letivo):
    turma = {"nome": nome, "ano_letivo": ano_letivo}
    resultado = colecao.insert_one(turma)
    return resultado.inserted_id, turma


def listar():
    return (
        colecao
        .find({}, {"nome": 1, "ano_letivo": 1})
        .sort([("ano_letivo", -1), ("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter(turma_id):
    return colecao.find_one(
        {"_id": ObjectId(turma_id)},
        {"nome": 1, "ano_letivo": 1},
    )


def adicionar_profissional(turma_id, profissional_id):
    return colecao.find_one_and_update(
        {"_id": ObjectId(turma_id)},
        {"$addToSet": {"profissionais_ids": profissional_id}},
        projection={"nome": 1, "ano_letivo": 1, "profissionais_ids": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def listar_por_profissional(profissional_id):
    return (
        colecao
        .find(
            {"profissionais_ids": profissional_id},
            {"nome": 1, "ano_letivo": 1},
        )
        .sort([("ano_letivo", -1), ("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter_atribuida_ao_profissional(turma_id, profissional_id):
    return colecao.find_one(
        {"_id": ObjectId(turma_id), "profissionais_ids": profissional_id},
        {"nome": 1, "ano_letivo": 1},
    )


def obter_para_chat(turma_id, profissional_id):
    return colecao.find_one(
        {"_id": turma_id, "profissionais_ids": profissional_id},
        {"_id": 1},
    )
