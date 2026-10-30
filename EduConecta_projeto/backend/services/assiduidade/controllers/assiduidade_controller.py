"""Controller: rotas HTTP de assiduidade — validam o pedido, delegam a
lógica de dados/autorização ao `models.assiduidade` e formatam a resposta.

Autenticação e permissão por rota (quem pode chamar o quê) já foram
decididas no `before_request` de `app.py`; aqui assume-se que `g.conta_id`
existe e que o perfil já tem acesso de princípio à operação.
"""

from datetime import timedelta

from bson import ObjectId
from flask import Blueprint, g, jsonify, request
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.assiduidade as modelo
from utils.eventos import publicar
from utils.http_client import consultar, erro

bp = Blueprint("assiduidade", __name__)


@bp.get("/turmas/<turma_id>/assiduidade")
def consultar_turma(turma_id):
    """Lista a assiduidade de todos os alunos de uma turma num dia.

    Só acessível a docente/educadora (ver `permissoes` em `app.py`), e só
    para turmas às quais o profissional autenticado está associado — essa
    verificação acontece em `modelo.alunos_autorizados`, que consulta o
    serviço `escolar`. Devolve também uma `contagem` por estado, útil para
    um resumo rápido no frontend (ex. "3 presentes, 1 falta, 2 por marcar").
    """
    if set(request.args) != {"data"} or len(request.args.getlist("data")) != 1:
        return erro("invalid_query", "Envia apenas data=AAAA-MM-DD.", 400)
    try:
        dia = modelo.data_iso(request.args["data"]).isoformat()
    except ValueError:
        return erro("invalid_date", "Data inválida; usa AAAA-MM-DD.", 400)
    tid, alunos, falha = modelo.alunos_autorizados(turma_id)
    if falha is not None:
        return falha
    ids = [str(ObjectId(a["id"])) for a in alunos]
    try:
        docs = modelo.procurar_marcacoes_turma(dia, ids)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar as marcações.", 503)
    itens = []
    contagem = {e: 0 for e in sorted(modelo.ESTADOS)}
    for aluno, aid in zip(alunos, ids):
        doc = docs.get(aid)
        item = modelo.serializar(doc, aid, dia, profissional=True)
        item["nome"] = aluno.get("nome")
        item["editavel"] = doc is None or doc["turma_id"] == tid
        contagem[item["estado"]] += 1
        itens.append(item)
    return jsonify({"turma_id": tid, "data": dia, "alunos": itens,
                    "quantidade": len(itens), "contagem": contagem}), 200


@bp.put("/turmas/<turma_id>/alunos/<aluno_id>/assiduidade/<dia>")
def marcar(turma_id, aluno_id, dia):
    """Marca o estado de assiduidade de um aluno num dia (presente/falta/por_marcar).

    Exige `versao` no corpo para controlo de concorrência otimista: se
    outra pessoa já tiver alterado a marcação entretanto, `modelo.marcar_estado`
    devolve None e respondemos 409, obrigando o cliente a reconsultar antes
    de tentar outra vez (evita perder uma alteração concorrente em silêncio).
    """
    if not ObjectId.is_valid(aluno_id):
        return erro("invalid_student_id", "Identificador de aluno inválido.", 400)
    aid = str(ObjectId(aluno_id))
    try:
        dia = modelo.data_iso(dia).isoformat()
    except ValueError:
        return erro("invalid_date", "Data inválida; usa AAAA-MM-DD.", 400)
    if request.args:
        return erro("invalid_query", "Esta operação não aceita parâmetros de pesquisa.", 400)
    if not request.is_json:
        return erro("unsupported_media_type", "Envia application/json.", 415)
    dados = request.get_json(silent=True)
    if (not isinstance(dados, dict) or set(dados) != {"estado", "versao"}
            or not isinstance(dados.get("estado"), str) or dados["estado"] not in modelo.ESTADOS
            or type(dados.get("versao")) is not int or not 0 <= dados["versao"] < 2**31):
        return erro("invalid_fields", "Envia estado (presente, falta ou por_marcar) e versao inteira não negativa.", 400)
    tid, alunos, falha = modelo.alunos_autorizados(turma_id)
    if falha is not None:
        return falha
    if not any(str(ObjectId(a["id"])) == aid for a in alunos):
        return erro("student_not_accessible", "Aluno não pertence à turma acessível.", 404)
    try:
        doc = modelo.marcar_estado(aid, tid, dia, dados["estado"], dados["versao"], g.conta_id)
    except DuplicateKeyError:
        return erro("attendance_conflict", "A marcação mudou ou pertence a outra turma. Atualiza a consulta.", 409)
    except PyMongoError:
        return erro("database_unavailable", "Gravação não confirmada. Consulta antes de repetir.", 503)
    if doc is None:
        return erro("attendance_conflict", "A marcação mudou. Atualiza a consulta.", 409)
    if doc["estado"] == "falta":
        publicar("falta.registada", {"aluno_id": aid, "turma_id": tid, "data": dia})
    return jsonify(modelo.serializar(doc, aid, dia, profissional=True)), 200


@bp.get("/alunos/<aluno_id>/assiduidade")
def consultar_educando(aluno_id):
    """Histórico de assiduidade de um educando, visto pelo encarregado de educação.

    Só devolve dias dentro de um intervalo de no máximo 31 dias (`inicio`
    a `fim` inclusive) para limitar o tamanho da resposta. Confirma que o
    aluno pertence mesmo a este encarregado consultando `GET /me/alunos`
    no `escolar`, com a mesma cautela de `alunos_autorizados` quanto à
    lista poder estar incompleta pelo limite de paginação.
    """
    if not ObjectId.is_valid(aluno_id):
        return erro("invalid_student_id", "Identificador de aluno inválido.", 400)
    aid = str(ObjectId(aluno_id))
    if (set(request.args) != {"inicio", "fim"}
            or any(len(request.args.getlist(c)) != 1 for c in ("inicio", "fim"))):
        return erro("invalid_query", "Envia inicio e fim no formato AAAA-MM-DD.", 400)
    try:
        inicio = modelo.data_iso(request.args["inicio"])
        fim = modelo.data_iso(request.args["fim"])
        if not 0 <= (fim - inicio).days <= 30:
            raise ValueError()
    except ValueError:
        return erro("invalid_date_range", "Intervalo inválido; máximo de 31 dias inclusive.", 400)
    dados, falha = consultar("http://escolar:8000/me/alunos")
    if falha is not None:
        return falha
    alunos = dados.get("alunos")
    if (not isinstance(alunos, list) or any(not isinstance(a, dict)
            or not isinstance(a.get("id"), str) or not ObjectId.is_valid(a["id"])
            for a in alunos)):
        return erro("dependency_unavailable", "Resposta escolar inesperada.", 503)
    if not any(str(ObjectId(a["id"])) == aid for a in alunos):
        if type(dados.get("limite")) is int and len(alunos) >= dados["limite"]:
            return erro("school_list_limit", "A lista escolar pode estar incompleta.", 409)
        return erro("student_not_accessible", "Educando não acessível.", 404)
    try:
        docs = modelo.procurar_marcacoes_aluno(aid, inicio, fim)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar as marcações.", 503)
    itens = []
    for deslocamento in range((fim - inicio).days + 1):
        texto = (inicio + timedelta(days=deslocamento)).isoformat()
        itens.append(modelo.serializar(docs.get(texto), aid, texto))
    return jsonify({"aluno_id": aid, "inicio": inicio.isoformat(), "fim": fim.isoformat(),
                    "registos": itens, "quantidade": len(itens)}), 200
