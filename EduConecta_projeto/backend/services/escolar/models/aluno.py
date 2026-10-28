"""Model: acesso aos dados da coleção `alunos` — sem validação nem formatação de resposta."""

from bson import ObjectId
from pymongo import ReturnDocument

from db import database

colecao = database["alunos"]


def listar():
    """Até 50 alunos, por ordem de inserção (campos resumidos para listagem)."""
    return (
        colecao
        .find({}, {"nome": 1, "numero_processo": 1})
        .sort("_id", 1)
        .limit(50)
    )


def criar(nome, numero_processo):
    """Insere um aluno novo; devolve (id gerado, documento inserido)."""
    aluno = {"nome": nome, "numero_processo": numero_processo}
    resultado = colecao.insert_one(aluno)
    return resultado.inserted_id, aluno


def obter(aluno_id):
    """Devolve um aluno pelo id, ou None se não existir."""
    return colecao.find_one(
        {"_id": ObjectId(aluno_id)},
        {"nome": 1, "numero_processo": 1},
    )


def atualizar(aluno_id, alteracoes):
    """Aplica um $set parcial (nome e/ou numero_processo) e devolve o documento já atualizado."""
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id)},
        {"$set": alteracoes},
        projection={"nome": 1, "numero_processo": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def definir_turma(aluno_id, turma_id):
    """Associa o aluno a uma turma (substitui a anterior, se existir)."""
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id)},
        {"$set": {"turma_id": turma_id}},
        projection={"nome": 1, "numero_processo": 1, "turma_id": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def listar_por_turma(turma_id):
    """Alunos de uma turma (até 50), ordenados por nome."""
    return (
        colecao
        .find({"turma_id": turma_id}, {"nome": 1, "numero_processo": 1})
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def adicionar_encarregado(aluno_id, encarregado_id):
    """Acrescenta um encarregado à lista do aluno (idempotente: $addToSet não duplica)."""
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id)},
        {"$addToSet": {"encarregados_ids": encarregado_id}},
        projection={"nome": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def obter_com_encarregados(aluno_id):
    """Aluno + a lista bruta de ids de encarregados (para o controller resolver os nomes)."""
    return colecao.find_one(
        {"_id": ObjectId(aluno_id)},
        {"nome": 1, "encarregados_ids": 1},
    )


def listar_por_encarregado(encarregado_id):
    """Alunos associados a um encarregado específico (até 50), ordenados por nome."""
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
    """Confirma que o aluno existe e está ligado a este encarregado; usado na validação de chat."""
    return colecao.find_one(
        {"_id": aluno_id, "encarregados_ids": encarregado_id},
        {"turma_id": 1},
    )
