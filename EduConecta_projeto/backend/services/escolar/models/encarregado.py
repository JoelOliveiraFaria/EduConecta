"""Model: acesso aos dados da coleção `encarregados_educacao` — sem validação nem formatação de resposta."""

from bson import ObjectId
from pymongo import ReturnDocument

from db import database

colecao = database["encarregados_educacao"]


def criar(nome, telefone):
    """Insere um encarregado de educação novo; devolve (id gerado, documento inserido)."""
    encarregado = {"nome": nome, "telefone": telefone}
    resultado = colecao.insert_one(encarregado)
    return resultado.inserted_id, encarregado


def listar():
    """Até 50 encarregados de educação, por nome."""
    return (
        colecao
        .find({}, {"nome": 1, "telefone": 1})
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter(encarregado_id):
    """Devolve um encarregado pelo id, ou None se não existir."""
    return colecao.find_one(
        {"_id": ObjectId(encarregado_id)},
        {"nome": 1},
    )


def obter_por_utilizador(utilizador_id):
    """Encontra o registo de encarregado ligado a esta conta de utilizador (sessão atual)."""
    return colecao.find_one(
        {"utilizador_id": utilizador_id},
        {"nome": 1},
    )


def obter_com_utilizador(encarregado_id):
    """Encarregado + o utilizador_id já associado (para o controller confirmar antes de reatribuir)."""
    return colecao.find_one(
        {"_id": ObjectId(encarregado_id)},
        {"nome": 1, "utilizador_id": 1},
    )


def associar_utilizador(encarregado_id, conta_id):
    """Liga uma conta ao encarregado — só se ainda não tiver conta associada,
    ou se já for exatamente esta (operação idempotente). O filtro `$or` evita
    sobrescrever uma associação já existente com outra conta numa condição
    de corrida; devolve None se a condição não bater certo (já associado a outra conta)."""
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
    """Confirma que existe um registo de encarregado ligado a esta conta; usado na validação de chat."""
    return colecao.find_one(
        {"utilizador_id": utilizador_id},
        {"_id": 1},
    )


def listar_por_ids(ids):
    """Encarregados cujo _id está na lista dada (até 50) — usado para resolver os
    encarregados_ids guardados num aluno."""
    return (
        colecao
        .find({"_id": {"$in": ids}}, {"nome": 1, "telefone": 1})
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )
