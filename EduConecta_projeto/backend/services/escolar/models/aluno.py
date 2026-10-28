from bson import ObjectId
from pymongo import ReturnDocument

from db import database

colecao = database["alunos"]


def listar():
    return (
        colecao
        .find({}, {"nome": 1, "numero_processo": 1})
        .sort("_id", 1)
        .limit(50)
    )


def criar(nome, numero_processo):
    aluno = {"nome": nome, "numero_processo": numero_processo}
    resultado = colecao.insert_one(aluno)
    return resultado.inserted_id, aluno


def obter(aluno_id):
    return colecao.find_one(
        {"_id": ObjectId(aluno_id)},
        {"nome": 1, "numero_processo": 1},
    )


def atualizar(aluno_id, alteracoes):
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id)},
        {"$set": alteracoes},
        projection={"nome": 1, "numero_processo": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def definir_turma(aluno_id, turma_id):
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id)},
        {"$set": {"turma_id": turma_id}},
        projection={"nome": 1, "numero_processo": 1, "turma_id": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def listar_por_turma(turma_id):
    return (
        colecao
        .find({"turma_id": turma_id}, {"nome": 1, "numero_processo": 1})
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def adicionar_encarregado(aluno_id, encarregado_id):
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id)},
        {"$addToSet": {"encarregados_ids": encarregado_id}},
        projection={"nome": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def obter_com_encarregados(aluno_id):
    return colecao.find_one(
        {"_id": ObjectId(aluno_id)},
        {"nome": 1, "encarregados_ids": 1},
    )


def listar_por_encarregado(encarregado_id):
    return (
        colecao
        .find(
            {"encarregados_ids": encarregado_id},
            {"nome": 1, "numero_processo": 1, "turma_id": 1},
        )
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter_para_chat(aluno_id, encarregado_id):
    return colecao.find_one(
        {"_id": aluno_id, "encarregados_ids": encarregado_id},
        {"turma_id": 1},
    )
