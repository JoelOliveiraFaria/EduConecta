"""Model: acesso aos dados da coleção `turmas` — sem validação nem formatação de resposta."""

from bson import ObjectId
from pymongo import ReturnDocument

from db import database

colecao = database["turmas"]

# "creche" — aceita registo diário (diario) e faltas (assiduidade).
# "basico" — só aceita faltas; o diario recusa turmas deste tipo.
TIPOS = {"creche", "basico"}


def criar(nome, ano_letivo, tipo):
    """Insere uma turma nova; devolve (id gerado, documento inserido)."""
    turma = {"nome": nome, "ano_letivo": ano_letivo, "tipo": tipo}
    resultado = colecao.insert_one(turma)
    return resultado.inserted_id, turma


def listar():
    """Até 50 turmas, mais recentes (ano letivo) primeiro, depois por nome."""
    return (
        colecao
        .find({}, {"nome": 1, "ano_letivo": 1, "tipo": 1})
        .sort([("ano_letivo", -1), ("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter(turma_id):
    """Devolve uma turma pelo id, ou None se não existir."""
    return colecao.find_one(
        {"_id": ObjectId(turma_id)},
        {"nome": 1, "ano_letivo": 1, "tipo": 1},
    )


def adicionar_profissional(turma_id, profissional_id):
    """Associa um profissional à turma (idempotente: $addToSet não duplica)."""
    return colecao.find_one_and_update(
        {"_id": ObjectId(turma_id)},
        {"$addToSet": {"profissionais_ids": profissional_id}},
        projection={"nome": 1, "ano_letivo": 1, "tipo": 1, "profissionais_ids": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def listar_por_profissional(profissional_id):
    """Turmas atribuídas a um profissional (até 50) — usado em /me/turmas."""
    return (
        colecao
        .find(
            {"profissionais_ids": profissional_id},
            {"nome": 1, "ano_letivo": 1, "tipo": 1},
        )
        .sort([("ano_letivo", -1), ("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter_atribuida_ao_profissional(turma_id, profissional_id):
    """Devolve a turma só se este profissional estiver mesmo atribuído a ela
    (filtra pelos dois campos na própria query, em vez de buscar e comparar
    depois — garante que ninguém vê turmas que não são suas)."""
    return colecao.find_one(
        {"_id": ObjectId(turma_id), "profissionais_ids": profissional_id},
        {"nome": 1, "ano_letivo": 1, "tipo": 1},
    )


def obter_para_chat(turma_id, profissional_id):
    """Confirma que a turma existe e tem este profissional atribuído; usado na validação de chat."""
    return colecao.find_one(
        {"_id": turma_id, "profissionais_ids": profissional_id},
        {"_id": 1},
    )


def obter_detalhe(turma_id):
    """Turma com a lista de profissionais atribuídos."""
    return colecao.find_one(
        {"_id": ObjectId(turma_id)},
        {"nome": 1, "ano_letivo": 1, "tipo": 1, "profissionais_ids": 1},
    )


def profissionais_atribuidos(turma_id):
    """Só a lista de profissionais_ids da turma, ou None se a turma não existir
    (usado para verificar a regra "1 docente por turma" antes de associar)."""
    turma = colecao.find_one({"_id": ObjectId(turma_id)}, {"profissionais_ids": 1})
    if turma is None:
        return None
    return turma.get("profissionais_ids", [])


def esta_atribuido(turma_id, profissional_id):
    """True se este profissional estiver na lista de profissionais da turma."""
    return colecao.find_one(
        {"_id": ObjectId(turma_id), "profissionais_ids": ObjectId(profissional_id)},
        {"_id": 1},
    ) is not None
