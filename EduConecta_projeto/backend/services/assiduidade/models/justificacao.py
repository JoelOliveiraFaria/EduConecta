"""Model: acesso aos dados de justificações de faltas (RF18, RF20, RF21,
RF22) e ao anexo opcional guardado em GridFS.

Uma justificação tem sempre, no máximo, uma por falta (`_id` determinístico
`aluno_id:data`, igual ao padrão já usado em `models.assiduidade` para as
marcações) — não sabe nada de HTTP/Flask, isso é todo tratado no controller.
"""

from datetime import datetime, timedelta, timezone

from pymongo import ReturnDocument

from db import anexos_justificacao, justificacoes

ESTADOS = {"pendente", "aprovada", "rejeitada"}

# Prazo de submissão: 3 dias úteis a contar do dia da falta (fins de semana
# não contam). Não considera feriados — simplificação assumida para a Fase 1,
# sem calendário de feriados disponível.
PRAZO_DIAS_UTEIS = 3


def _id(aluno_id, dia):
    return f"{aluno_id}:{dia}"


def prazo_expirado(dia_falta, hoje=None):
    """True se já passaram mais de `PRAZO_DIAS_UTEIS` dias úteis desde a falta."""
    hoje = hoje or datetime.now(timezone.utc).date()
    restantes = PRAZO_DIAS_UTEIS
    cursor = dia_falta
    while restantes > 0:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:  # segunda=0 ... sexta=4
            restantes -= 1
    return hoje > cursor


def obter(aluno_id, dia):
    """Devolve a justificação de uma falta, ou None se nunca foi submetida."""
    return justificacoes.find_one({"_id": _id(aluno_id, dia)})


def submeter(aluno_id, turma_id, dia, motivo, anexo_id, anexo_nome, conta_id):
    """Regista a justificação submetida pelo encarregado. Fica `pendente`.

    Levanta DuplicateKeyError se já existir uma justificação para esta
    falta (só se pode submeter uma vez; para alterar, teria de se apagar
    e resubmeter — não implementado na Fase 1).
    """
    documento = {
        "_id": _id(aluno_id, dia),
        "aluno_id": aluno_id,
        "turma_id": turma_id,
        "data": dia,
        "motivo": motivo,
        "anexo_id": anexo_id,
        "anexo_nome": anexo_nome,
        "estado": "pendente",
        "motivo_rejeicao": None,
        "submetida_por": conta_id,
        "submetida_em": datetime.now(timezone.utc),
        "decidida_por": None,
        "decidida_em": None,
    }
    justificacoes.insert_one(documento)
    return documento


def decidir(aluno_id, dia, estado, motivo_rejeicao, conta_id):
    """Aprova ou rejeita uma justificação `pendente`.

    Devolve None se não existir justificação, ou se já tiver sido decidida
    antes (o filtro `estado: "pendente"` só encontra a primeira vez) —
    o controller trata isso como 409, não 404, para distinguir "nunca
    existiu" de "já foi decidida".
    """
    return justificacoes.find_one_and_update(
        {"_id": _id(aluno_id, dia), "estado": "pendente"},
        {
            "$set": {
                "estado": estado,
                "motivo_rejeicao": motivo_rejeicao,
                "decidida_por": conta_id,
                "decidida_em": datetime.now(timezone.utc),
            },
        },
        return_document=ReturnDocument.AFTER,
        upsert=False,
    )


def guardar_anexo(ficheiro_bytes, nome, content_type):
    """Grava o anexo em GridFS; devolve o seu id."""
    return anexos_justificacao.put(ficheiro_bytes, filename=nome, content_type=content_type)


def obter_anexo(anexo_id):
    """Devolve o ficheiro GridFS (com .read(), .filename, .content_type), ou None."""
    if not anexos_justificacao.exists(anexo_id):
        return None
    return anexos_justificacao.get(anexo_id)


def serializar(doc):
    """Converte o documento interno na forma pública devolvida pela API."""
    return {
        "aluno_id": doc["aluno_id"],
        "data": doc["data"],
        "motivo": doc.get("motivo"),
        "tem_anexo": doc.get("anexo_id") is not None,
        "estado": doc["estado"],
        "motivo_rejeicao": doc.get("motivo_rejeicao"),
        "submetida_em": doc["submetida_em"].isoformat(timespec="milliseconds"),
        "decidida_em": (
            doc["decidida_em"].isoformat(timespec="milliseconds")
            if doc.get("decidida_em")
            else None
        ),
    }
