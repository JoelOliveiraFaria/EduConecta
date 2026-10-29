"""Model: acesso aos dados de assiduidade e regras de validação/autorização
que dependem diretamente desses dados (datas, listas de alunos autorizadas).

Não sabe nada de HTTP/Flask para além das respostas de erro já formatadas
que recebe de `utils.http_client.erro` — quem decide o que fazer com elas
(devolvê-las ao cliente) é sempre o controller.
"""

from datetime import date, datetime, timezone

from bson import ObjectId
from pymongo import ReturnDocument

from db import registos
from utils.http_client import consultar, erro

# Estados possíveis de uma marcação de presença.
# "por_marcar" é o estado implícito de um aluno sem registo (nunca é
# gravado explicitamente na BD — só aparece quando serializamos um doc=None).
ESTADOS = {"presente", "falta", "por_marcar"}


def data_iso(valor):
    """Valida e converte uma string AAAA-MM-DD num `date`.

    Rejeita (ValueError) qualquer formato que não seja exatamente ISO-8601
    de data — incluindo datas "quase válidas" que o fromisoformat aceitaria
    de forma mais permissiva, porque comparamos o isoformat() de volta com
    o valor original.
    """
    if not isinstance(valor, str):
        raise ValueError()
    dia = date.fromisoformat(valor)
    if dia.isoformat() != valor:
        raise ValueError()
    return dia


def alunos_autorizados(turma_id):
    """Confirma que a turma existe e é acessível à conta autenticada,
    consultando `GET /me/turmas/<id>/alunos` no serviço `escolar`.

    O `escolar` já aplica aí a sua própria lógica de permissões (só devolve
    a turma se o profissional autenticado estiver associado a ela), por
    isso esta função não repete essa verificação — só valida a *forma* da
    resposta e devolve a lista de alunos que podem ser marcados.

    Devolve (turma_id, alunos, None) em caso de sucesso, ou
    (None, None, resposta_de_erro) em caso de falha.
    """
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
    # O endpoint do escolar pagina com um limite fixo: se a turma tiver
    # exatamente esse número de alunos, não há garantia de que a lista
    # esteja completa, por isso recusamos em vez de arriscar marcar
    # presenças com base numa lista parcial.
    if len(alunos) >= limite:
        return None, None, erro("school_list_limit", "A lista escolar atingiu o limite; não é possível garantir que esteja completa.", 409)
    return tid, alunos, None


def serializar(doc, aluno_id, dia, profissional=False):
    """Converte um documento de assiduidade (ou a sua ausência) na forma
    pública devolvida pela API.

    Um aluno sem documento para o dia é "por_marcar", versão 0 — por isso
    todos os campos têm um valor por omissão quando `doc` é None.
    `profissional=True` inclui `atualizado_por` (quem fez a última
    marcação), informação que só faz sentido mostrar a quem gere a turma,
    não ao encarregado de educação.
    """
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
    """Devolve, por aluno_id, o registo de assiduidade de um dia para a
    lista de alunos dada (um dicionário para lookup O(1) no controller)."""
    return {d["aluno_id"]: d for d in registos.find({"data": dia, "aluno_id": {"$in": ids}})}


def marcar_estado(aid, tid, dia, estado, versao, conta_id):
    """Cria ou atualiza a marcação de um aluno num dia, com controlo de
    concorrência otimista por versão.

    O `_id` é determinístico (`aluno:data`), o que torna o upsert seguro
    para duplicados. `versao == 0` só é aceite como upsert (primeira
    marcação); qualquer outro valor tem de corresponder exatamente à
    versão atual do documento, senão o filtro não encontra nada e
    `find_one_and_update` devolve None — sinal para o controller tratar
    como conflito (alguém marcou entretanto).
    """
    agora = datetime.now(timezone.utc)
    return registos.find_one_and_update(
        {"_id": f"{aid}:{dia}", "turma_id": tid, "versao": versao},
        {"$set": {"estado": estado, "atualizado_em": agora,
                  "atualizado_por": conta_id},
         "$setOnInsert": {"aluno_id": aid, "data": dia, "criado_em": agora},
         "$inc": {"versao": 1}},
        upsert=versao == 0, return_document=ReturnDocument.AFTER,
    )


def obter_registo(aid, dia):
    """Devolve o registo de assiduidade de um aluno num dia, ou None se não
    existir (usado para confirmar que há mesmo uma falta antes de aceitar
    uma justificação)."""
    return registos.find_one({"_id": f"{aid}:{dia}"})


def procurar_marcacoes_aluno(aid, inicio, fim):
    """Devolve, por data (string ISO), as marcações de um aluno entre
    `inicio` e `fim` (inclusive em ambas as pontas)."""
    return {d["data"]: d for d in registos.find({
        "aluno_id": aid, "data": {"$gte": inicio.isoformat(), "$lte": fim.isoformat()},
    })}
