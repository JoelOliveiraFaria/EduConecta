"""Model: acesso aos dados da coleção `alunos` — sem validação nem formatação de resposta."""

from datetime import datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from db import database

colecao = database["alunos"]

# Eliminar um aluno é soft-delete: marca eliminado=True em vez de apagar o
# documento, porque outros serviços (diario, assiduidade) têm registos
# históricos que referenciam o aluno_id e não devem ficar a apontar para um
# id que simplesmente desapareceu. Por isso todas as queries abaixo excluem
# alunos eliminados, como se já não existissem para efeitos de uso normal.
NAO_ELIMINADO = {"eliminado": {"$ne": True}}


def listar():
    """Até 50 alunos (não eliminados), por ordem de inserção."""
    return (
        colecao
        .find(NAO_ELIMINADO, {"nome": 1, "numero_processo": 1})
        .sort("_id", 1)
        .limit(50)
    )


def criar(nome, numero_processo, data_nascimento=None, morada=""):
    """Insere um aluno novo; devolve (id gerado, documento inserido)."""
    aluno = {
        "nome": nome,
        "numero_processo": numero_processo,
        "data_nascimento": data_nascimento,
        "morada": morada,
    }
    resultado = colecao.insert_one(aluno)
    return resultado.inserted_id, aluno


def obter(aluno_id):
    """Devolve um aluno (não eliminado) pelo id, ou None se não existir/estiver eliminado."""
    return colecao.find_one(
        {"_id": ObjectId(aluno_id), **NAO_ELIMINADO},
        {"nome": 1, "numero_processo": 1, "turma_id": 1, "data_nascimento": 1, "morada": 1},
    )


def atualizar(aluno_id, alteracoes):
    """Aplica um $set parcial (nome, numero_processo, data_nascimento e/ou
    morada) e devolve o documento já atualizado."""
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id), **NAO_ELIMINADO},
        {"$set": alteracoes},
        projection={"nome": 1, "numero_processo": 1, "data_nascimento": 1, "morada": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def eliminar(aluno_id, eliminado_por):
    """Soft-delete: marca o aluno como eliminado em vez de remover o documento.

    Devolve o documento como estava antes de ser eliminado (None se já não
    existir ou já estar eliminado), para o controller poder confirmar que
    a operação teve efeito.
    """
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id), **NAO_ELIMINADO},
        {
            "$set": {
                "eliminado": True,
                "eliminado_em": datetime.now(timezone.utc),
                "eliminado_por": eliminado_por,
            },
        },
        projection={"nome": 1},
        return_document=ReturnDocument.BEFORE,
        upsert=False,
    )


def definir_turma(aluno_id, turma_id):
    """Associa o aluno a uma turma (substitui a anterior, se existir)."""
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id), **NAO_ELIMINADO},
        {"$set": {"turma_id": turma_id}},
        projection={"nome": 1, "numero_processo": 1, "turma_id": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def listar_por_turma(turma_id):
    """Alunos de uma turma (até 50, não eliminados), ordenados por nome."""
    return (
        colecao
        .find({"turma_id": turma_id, **NAO_ELIMINADO}, {"nome": 1, "numero_processo": 1})
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def listar_encarregados_ids_por_turma(turma_id):
    """Lista achatada (sem duplicados) dos encarregados_ids de todos os
    alunos (não eliminados) de uma turma — usada pelo endpoint interno que
    resolve destinatários de notificações (Fase 2), não precisa dos
    restantes dados do aluno."""
    ids = set()
    for aluno in colecao.find(
        {"turma_id": turma_id, **NAO_ELIMINADO}, {"encarregados_ids": 1}
    ).limit(50):
        ids.update(aluno.get("encarregados_ids", []))
    return list(ids)


def adicionar_encarregado(aluno_id, encarregado_id):
    """Acrescenta um encarregado à lista do aluno (idempotente: $addToSet não duplica)."""
    return colecao.find_one_and_update(
        {"_id": ObjectId(aluno_id), **NAO_ELIMINADO},
        {"$addToSet": {"encarregados_ids": encarregado_id}},
        projection={"nome": 1},
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def obter_com_encarregados(aluno_id):
    """Aluno + a lista bruta de ids de encarregados (para o controller resolver os nomes)."""
    return colecao.find_one(
        {"_id": ObjectId(aluno_id), **NAO_ELIMINADO},
        {"nome": 1, "encarregados_ids": 1},
    )


def listar_por_encarregado(encarregado_id):
    """Alunos associados a um encarregado específico (até 50, não eliminados), ordenados por nome."""
    return (
        colecao
        .find(
            {"encarregados_ids": encarregado_id, **NAO_ELIMINADO},
            {"nome": 1, "numero_processo": 1, "turma_id": 1},
        )
        .sort([("nome", 1), ("_id", 1)])
        .limit(50)
    )


def obter_para_chat(aluno_id, encarregado_id):
    """Confirma que o aluno existe (não eliminado) e está ligado a este encarregado."""
    return colecao.find_one(
        {"_id": aluno_id, "encarregados_ids": encarregado_id, **NAO_ELIMINADO},
        {"turma_id": 1},
    )
