"""Model: acesso aos dados da coleção `comunicados` — sem validação de input
nem verificação de permissões (isso é feito nos controllers, via
utils/acesso.py, antes de chamar estas funções)."""

from datetime import datetime, timezone

from bson import ObjectId

from db import database


def serializar(documento):
    """Converte um documento Mongo no formato JSON devolvido pela API."""
    return {
        "id": str(documento["_id"]),
        "turma_id": documento["turma_id"],
        "titulo": documento["titulo"],
        "texto": documento["texto"],
        "criado_em": documento["criado_em"].isoformat(
            timespec="milliseconds"
        ),
    }


def criar(turma_id, titulo, texto, criado_por):
    """Publica um novo comunicado numa turma."""
    documento = {
        "_id": ObjectId(),
        "turma_id": turma_id,
        "titulo": titulo,
        "texto": texto,
        "criado_por": criado_por,
        "criado_em": datetime.now(timezone.utc),
    }
    database["comunicados"].insert_one(documento)
    return documento


def listar_por_turma(turma_id, pagina, limite):
    """Comunicados de uma turma, mais recentes primeiro, paginados (pede limite+1
    para o controller saber se existe próxima página sem fazer um count à parte)."""
    return list(
        database["comunicados"]
        .find({"turma_id": turma_id})
        .sort([("criado_em", -1), ("_id", -1)])
        .skip((pagina - 1) * limite)
        .limit(limite + 1)
    )


def obter_editavel(comunicado_id, turma_id, criado_por):
    """Existe só se o comunicado for desta turma E tiver sido criado por esta conta
    (quem publica só pode anexar fotos/vídeos aos seus próprios comunicados)."""
    return database["comunicados"].find_one(
        {
            "_id": ObjectId(comunicado_id),
            "turma_id": turma_id,
            "criado_por": criado_por,
        },
        {"_id": 1},
    )


def obter_acessivel(comunicado_id, turma_id):
    """Existe se o comunicado pertencer a esta turma — usado para leitura (sem
    restrição de autor, ao contrário de obter_editavel)."""
    return database["comunicados"].find_one(
        {"_id": ObjectId(comunicado_id), "turma_id": turma_id},
        {"_id": 1},
    )
