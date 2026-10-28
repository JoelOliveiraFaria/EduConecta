"""Model: acesso aos dados da coleção `registos` (diário diário dos alunos).

Cada função faz só a operação MongoDB correspondente e devolve dados crus —
nenhuma validação de input nem formatação de resposta HTTP vive aqui, isso
é dos controllers.
"""

from pymongo import ReturnDocument

from db import CAMPOS_TEXTO, database, registos


def contar_colecoes():
    """Lista as coleções da base de dados — usado só pelo /ready para confirmar ligação."""
    return database.list_collection_names()


def serializar(documento):
    """Converte um documento Mongo no dicionário devolvido em JSON.

    Garante que todos os campos de texto aparecem mesmo que não tenham sido
    definidos (`documento.get(campo, "")`), e converte as datas para ISO 8601.
    """
    resultado = {
        "id": documento["_id"],
        "aluno_id": documento["aluno_id"],
        "turma_id": documento["turma_id"],
        "data": documento["data"],
        **{
            campo: documento.get(campo, "")
            for campo in CAMPOS_TEXTO
        },
        "criado_por": documento["criado_por"],
        "criado_em": documento["criado_em"].isoformat(
            timespec="milliseconds"
        ),
    }

    if documento.get("atualizado_em") is not None:
        resultado["atualizado_em"] = documento["atualizado_em"].isoformat(
            timespec="milliseconds"
        )

    return resultado


def inserir(documento):
    """Grava um novo registo diário.

    O `_id` é montado pelo controller como `aluno_id:data` — é essa chave
    composta que impede dois registos do mesmo aluno na mesma data (o Mongo
    rejeita com DuplicateKeyError, apanhado no controller).
    """
    return registos.insert_one(documento)


def listar_por_aluno_turma(aluno_id, turma_id, limite=31):
    """Devolve os registos de um aluno numa turma, mais recentes primeiro."""
    return (
        registos
        .find({"aluno_id": aluno_id, "turma_id": turma_id})
        .sort("data", -1)
        .limit(limite)
    )


def atualizar(aluno_id, turma_id, data_registo, criado_por, alteracoes):
    """Atualiza um registo existente, aplicando o filtro completo (aluno, turma e
    autor original) para que só quem criou o registo o possa editar."""
    return registos.find_one_and_update(
        {
            "_id": f"{aluno_id}:{data_registo}",
            "aluno_id": aluno_id,
            "turma_id": turma_id,
            "criado_por": criado_por,
        },
        {"$set": alteracoes},
        return_document=ReturnDocument.AFTER,
    )
