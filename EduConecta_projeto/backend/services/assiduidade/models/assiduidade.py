from datetime import date, datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from db import registos
from utils.http_client import consultar, erro

ESTADOS = {"presente", "falta", "por_marcar"}


def data_iso(valor):
    if not isinstance(valor, str):
        raise ValueError()
    dia = date.fromisoformat(valor)
    if dia.isoformat() != valor:
        raise ValueError()
    return dia


def alunos_autorizados(turma_id):
    if not ObjectId.is_valid(turma_id):
        return None, None, erro("invalid_class_id", "Identificador de turma inválido.", 400)
    tid = str(ObjectId(turma_id))
    dados, falha = consultar(f"http://escolar:8000/me/turmas/{tid}/alunos")
    if falha is not None:
        return None, None, falha
    alunos = dados.get("alunos")
    turma = dados.get("turma")
    quantidade = dados.get("quantidade")
    limite = dados.get("limite")
    if (not isinstance(alunos, list) or not isinstance(turma, dict)
            or turma.get("id") != tid or type(quantidade) is not int
            or quantidade != len(alunos) or type(limite) is not int
            or limite <= 0 or any(not isinstance(a, dict)
            or not isinstance(a.get("id"), str) or not ObjectId.is_valid(a["id"])
            or a.get("turma_id") != tid for a in alunos)):
        return None, None, erro("dependency_unavailable", "Resposta escolar inesperada.", 503)
    if len(alunos) >= limite:
        return None, None, erro("school_list_limit", "A lista escolar atingiu o limite; não é possível garantir que esteja completa.", 409)
    return tid, alunos, None


def serializar(doc, aluno_id, dia, profissional=False):
    item = {"aluno_id": aluno_id, "data": dia,
            "estado": doc["estado"] if doc else "por_marcar",
            "versao": doc["versao"] if doc else 0,
            "atualizado_em": doc["atualizado_em"].isoformat(timespec="milliseconds") if doc else None}
    if doc:
        item["turma_id"] = doc["turma_id"]
    if profissional:
        item["atualizado_por"] = doc["atualizado_por"] if doc else None
    return item


def procurar_marcacoes_turma(dia, ids):
    return {d["aluno_id"]: d for d in registos.find({"data": dia, "aluno_id": {"$in": ids}})}


def marcar_estado(aid, tid, dia, estado, versao, conta_id):
    agora = datetime.now(timezone.utc)
    return registos.find_one_and_update(
        {"_id": f"{aid}:{dia}", "turma_id": tid, "versao": versao},
        {"$set": {"estado": estado, "atualizado_em": agora,
                  "atualizado_por": conta_id},
         "$setOnInsert": {"aluno_id": aid, "data": dia, "criado_em": agora},
         "$inc": {"versao": 1}},
        upsert=versao == 0, return_document=ReturnDocument.AFTER,
    )


def procurar_marcacoes_aluno(aid, inicio, fim):
    return {d["data"]: d for d in registos.find({
        "aluno_id": aid, "data": {"$gte": inicio.isoformat(), "$lte": fim.isoformat()},
    })}
