"""Controller: justificação de faltas (RF18, RF20, RF21, RF22).

RF20 — o encarregado de educação submete a justificação (texto e/ou
anexo). RF21/RF22 — qualquer docente ou educadora atribuído à turma da
falta pode aprovar ou rejeitar; é essa mesma decisão que cobre o RF18
("o profissional pode aceitar ou não a justificação"), não há um caminho
institucional em separado. Não existe o conceito de "diretor de turma":
o professor (docente) é sempre o único atribuído como tal a uma turma
(ver escolar: regra de 1 docente por turma), mas isso não lhe dá nenhum
poder extra aqui — a educadora decide da mesma forma.
"""

from io import BytesIO

from bson import ObjectId
from flask import g, jsonify, request, send_file
from gridfs.errors import CorruptGridFile, NoFile
from pymongo.errors import DuplicateKeyError, PyMongoError

import models.assiduidade as modelo_assiduidade
import models.justificacao as modelo_justificacao
from controllers.assiduidade_controller import bp
from db import MAX_ANEXO_BYTES
from utils.eventos import publicar
from utils.http_client import consultar, erro


def _validar_aluno_dia(aluno_id, dia):
    """Valida o formato de aluno_id/dia; devolve (aid, dia_iso, dia_date, None)
    ou (None, None, None, resposta_de_erro)."""
    if not ObjectId.is_valid(aluno_id):
        return None, None, None, erro("invalid_student_id", "Identificador de aluno inválido.", 400)
    try:
        dia_date = modelo_assiduidade.data_iso(dia)
    except ValueError:
        return None, None, None, erro("invalid_date", "Data inválida; usa AAAA-MM-DD.", 400)
    return str(ObjectId(aluno_id)), dia_date.isoformat(), dia_date, None


def _confirmar_encarregado(aid):
    """Confirma que o encarregado autenticado é mesmo encarregado deste aluno
    (mesma cautela de limite de paginação que consultar_educando)."""
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
    return None


def _confirmar_profissional_turma(turma_id):
    """Confirma que o profissional autenticado (docente ou educadora) está
    atribuído a esta turma — reaproveita a mesma verificação já usada para
    consultar/marcar assiduidade (`alunos_autorizados`), já que qualquer
    profissional atribuído pode decidir justificações (não há "diretor")."""
    _tid, _alunos, falha = modelo_assiduidade.alunos_autorizados(turma_id)
    return falha


@bp.post("/alunos/<aluno_id>/faltas/<dia>/justificacao")
def submeter_justificacao(aluno_id, dia):
    """RF20: o encarregado submete a justificação de uma falta (texto e/ou anexo)."""
    aid, dia_iso, dia_date, falha = _validar_aluno_dia(aluno_id, dia)
    if falha is not None:
        return falha

    falha = _confirmar_encarregado(aid)
    if falha is not None:
        return falha

    if request.mimetype != "multipart/form-data":
        return erro("unsupported_media_type", "Envia multipart/form-data.", 415)

    campos_forma = set(request.form) - {"motivo"}
    campos_ficheiro = set(request.files) - {"anexo"}
    if campos_forma or campos_ficheiro or len(request.files.getlist("anexo")) > 1:
        return erro("invalid_fields", "Envia apenas motivo (texto) e/ou anexo (ficheiro).", 400)

    motivo = request.form.get("motivo", "").strip() or None
    tem_anexo = "anexo" in request.files and request.files["anexo"].filename

    if motivo is None and not tem_anexo:
        return erro("invalid_fields", "Envia pelo menos motivo ou anexo.", 400)

    if motivo is not None and len(motivo) > 1000:
        return erro("invalid_fields", "O motivo não pode ter mais de 1000 caracteres.", 400)

    try:
        registo = modelo_assiduidade.obter_registo(aid, dia_iso)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar a falta.", 503)

    if registo is None or registo.get("estado") != "falta":
        return erro("absence_not_found", "Não existe uma falta registada nesse dia.", 404)

    if modelo_justificacao.prazo_expirado(dia_date):
        return erro(
            "deadline_expired",
            "O prazo de 3 dias úteis para justificar esta falta já passou.",
            409,
        )

    anexo_id = None
    anexo_nome = None

    if tem_anexo:
        ficheiro = request.files["anexo"]
        dados = ficheiro.stream.read(MAX_ANEXO_BYTES + 1)
        if len(dados) > MAX_ANEXO_BYTES:
            return erro("file_too_large", "O anexo deve ter até 5 MB.", 413)
        if not dados:
            return erro("empty_file", "O anexo está vazio.", 400)
        try:
            anexo_id = modelo_justificacao.guardar_anexo(
                dados, ficheiro.filename, ficheiro.mimetype
            )
        except PyMongoError:
            return erro("database_unavailable", "Não foi possível guardar o anexo.", 503)
        anexo_nome = ficheiro.filename

    try:
        doc = modelo_justificacao.submeter(
            aid, registo["turma_id"], dia_iso, motivo, anexo_id, anexo_nome, g.conta_id
        )
    except DuplicateKeyError:
        return erro("already_submitted", "Esta falta já tem uma justificação submetida.", 409)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível submeter a justificação.", 503)

    publicar("falta.justificacao.submetida", {
        "aluno_id": doc["aluno_id"],
        "turma_id": doc["turma_id"],
        "data": doc["data"],
    })

    return jsonify(modelo_justificacao.serializar(doc)), 201


@bp.put("/alunos/<aluno_id>/faltas/<dia>/justificacao/aprovar")
def aprovar_justificacao(aluno_id, dia):
    """RF18/RF21: um docente ou educadora atribuído à turma aprova a justificação."""
    return _decidir_justificacao(aluno_id, dia, "aprovada", None)


@bp.put("/alunos/<aluno_id>/faltas/<dia>/justificacao/rejeitar")
def rejeitar_justificacao(aluno_id, dia):
    """RF18/RF22: um docente ou educadora atribuído à turma rejeita a justificação, com motivo."""
    if not request.is_json:
        return erro("unsupported_media_type", "Envia application/json.", 415)
    dados = request.get_json(silent=True)
    if (not isinstance(dados, dict) or set(dados) != {"motivo_rejeicao"}
            or not isinstance(dados.get("motivo_rejeicao"), str)
            or not 1 <= len(dados["motivo_rejeicao"].strip()) <= 1000):
        return erro("invalid_fields", "Envia motivo_rejeicao (1 a 1000 caracteres).", 400)
    return _decidir_justificacao(aluno_id, dia, "rejeitada", dados["motivo_rejeicao"].strip())


def _decidir_justificacao(aluno_id, dia, estado, motivo_rejeicao):
    aid, dia_iso, _dia_date, falha = _validar_aluno_dia(aluno_id, dia)
    if falha is not None:
        return falha

    try:
        justificacao = modelo_justificacao.obter(aid, dia_iso)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar a justificação.", 503)

    if justificacao is None:
        return erro("justification_not_found", "Não existe justificação para esta falta.", 404)

    falha = _confirmar_profissional_turma(justificacao["turma_id"])
    if falha is not None:
        return falha

    try:
        doc = modelo_justificacao.decidir(aid, dia_iso, estado, motivo_rejeicao, g.conta_id)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível decidir a justificação.", 503)

    if doc is None:
        return erro(
            "justification_already_decided",
            "Esta justificação já foi decidida anteriormente.",
            409,
        )

    publicar("falta.justificacao.decidida", {
        "aluno_id": doc["aluno_id"],
        "data": doc["data"],
        "estado": doc["estado"],
        "destinatario_utilizador_id": doc["submetida_por"],
    })

    return jsonify(modelo_justificacao.serializar(doc)), 200


@bp.get("/alunos/<aluno_id>/faltas/<dia>/justificacao")
def consultar_justificacao(aluno_id, dia):
    """Consulta o estado da justificação de uma falta (RF19, extensão).

    Acessível ao encarregado do aluno, ou a um docente/educadora atribuído
    à turma da falta.
    """
    aid, dia_iso, _dia_date, falha = _validar_aluno_dia(aluno_id, dia)
    if falha is not None:
        return falha

    try:
        justificacao = modelo_justificacao.obter(aid, dia_iso)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar a justificação.", 503)

    if justificacao is None:
        return erro("justification_not_found", "Não existe justificação para esta falta.", 404)

    falha = _confirmar_acesso_leitura(aid, justificacao["turma_id"])
    if falha is not None:
        return falha

    return jsonify(modelo_justificacao.serializar(justificacao)), 200


@bp.get("/alunos/<aluno_id>/faltas/<dia>/justificacao/anexo")
def obter_anexo_justificacao(aluno_id, dia):
    """Descarrega o anexo da justificação de uma falta (ex: atestado)."""
    aid, dia_iso, _dia_date, falha = _validar_aluno_dia(aluno_id, dia)
    if falha is not None:
        return falha

    try:
        justificacao = modelo_justificacao.obter(aid, dia_iso)
    except PyMongoError:
        return erro("database_unavailable", "Não foi possível consultar a justificação.", 503)

    if justificacao is None or justificacao.get("anexo_id") is None:
        return erro("attachment_not_found", "Esta justificação não tem anexo.", 404)

    falha = _confirmar_acesso_leitura(aid, justificacao["turma_id"])
    if falha is not None:
        return falha

    try:
        ficheiro = modelo_justificacao.obter_anexo(justificacao["anexo_id"])
        if ficheiro is None:
            return erro("attachment_not_accessible", "Anexo não acessível.", 404)
        with ficheiro:
            if not 0 < ficheiro.length <= MAX_ANEXO_BYTES:
                return erro("attachment_unavailable", "Tamanho inesperado.", 503)
            dados = ficheiro.read(MAX_ANEXO_BYTES + 1)
            if len(dados) != ficheiro.length:
                return erro("attachment_unavailable", "Anexo incompleto.", 503)
    except (NoFile, CorruptGridFile, PyMongoError):
        return erro("attachment_unavailable", "Não foi possível ler o anexo.", 503)

    resposta = send_file(
        BytesIO(dados),
        mimetype=ficheiro.content_type or "application/octet-stream",
        download_name=justificacao.get("anexo_nome") or f"anexo-{justificacao['anexo_id']}",
        as_attachment=True,
        conditional=True, etag=False, max_age=0,
    )
    resposta.headers["Cache-Control"] = "no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


def _confirmar_acesso_leitura(aid, turma_id):
    """Encarregado do aluno, ou docente/educadora atribuído à turma, pode
    consultar/descarregar a justificação — qualquer outro perfil é bloqueado
    pelo `permissoes` de app.py antes de chegar aqui, isto só distingue
    qual dos dois caminhos de confirmação aplicar."""
    if g.perfil == "encarregado":
        return _confirmar_encarregado(aid)

    tid, alunos, falha = modelo_assiduidade.alunos_autorizados(turma_id)
    if falha is not None:
        return falha
    if not any(str(ObjectId(a["id"])) == aid for a in alunos):
        return erro("student_not_accessible", "Aluno não pertence à turma acessível.", 404)
    return None
