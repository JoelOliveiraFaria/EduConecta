"""Controller partilhado: autenticação + permissões para TODO o serviço escolar.

Este módulo não expõe rotas próprias — define o blueprint `bp` que os outros
controllers (aluno_controller, turma_controller, encarregado_controller,
profissional_controller, chat_controller) importam e usam para registar as
suas rotas. É aqui, e só aqui, que vivem:

  - `verificar_acesso_escolar`: corre antes de QUALQUER rota do blueprint
    (via `@bp.before_request`), valida o JWT contra o serviço auth e decide
    se o perfil autenticado pode aceder àquela rota.
  - `impedir_cache_dados_escolares`: acrescenta Cache-Control: no-store a
    todas as respostas do blueprint (dados escolares nunca devem ficar em
    cache do browser/proxy).
  - `obter_profissional_da_sessao`: helper partilhado pelas rotas "/me/..."
    que só fazem sentido para profissionais (turma_controller usa-o).

Centralizar isto num único ficheiro (em vez de repetir a verificação em cada
controller) garante que não há nenhuma rota do serviço que escape à
autenticação por engano — e é por isso que `health_controller.py` fica de
propósito FORA deste blueprint: /health e /ready têm de responder mesmo sem
token, por isso usam o seu próprio blueprint ("health"), sem este
before_request.

Nota sobre nomes de endpoint: o Flask prefixa o nome de cada rota com o nome
do blueprint (`<blueprint>.<função>`) — por isso as chaves de
PERMISSOES_PESSOAIS abaixo têm o prefixo "escolar." e não só o nome da
função. Se um dia estas rotas forem divididas por mais blueprints, este
prefixo muda e as chaves têm de ser atualizadas a condizer.
"""

from bson import ObjectId
from flask import Blueprint, g, jsonify, request

from utils.auth_client import obter_utilizador_da_sessao

bp = Blueprint("escolar", __name__)

# Rotas "pessoais" (/me/...) que um profissional ou encarregado pode usar
# sobre os SEUS PRÓPRIOS dados, mesmo sem ser admin. Qualquer rota que não
# esteja aqui só é acessível a quem tem perfil "admin" (ver a função abaixo).
PERMISSOES_PESSOAIS = {
    "escolar.listar_meus_alunos": {"encarregado"},
    "escolar.listar_minhas_turmas": {"docente", "educadora", "auxiliar"},
    "escolar.listar_alunos_minha_turma": {"docente", "educadora", "auxiliar"},
    "escolar.validar_participantes_chat": {"docente", "educadora", "encarregado"},
    # RF09: um profissional também pode editar um aluno (não só admin) — a
    # verificação de que o aluno pertence mesmo a uma turma do profissional
    # autenticado acontece dentro do próprio controller, não aqui (depende
    # dos dados do aluno, não só do perfil de quem pede). "admin" tem de
    # estar explícito aqui: ao entrar neste dict, a rota deixa de cair no
    # "elif ... == admin" mais abaixo — sem isto, um admin ficaria bloqueado.
    "escolar.atualizar_aluno": {"admin", "docente", "educadora", "auxiliar"},
    # Consultar o detalhe de uma turma (incluindo o diretor de turma) é
    # permitido a qualquer profissional atribuído a ela — o controller
    # confirma essa atribuição antes de devolver os dados. Mesma nota sobre
    # "admin" ter de estar explícito no conjunto.
    "escolar.obter_turma": {"admin", "docente", "educadora", "auxiliar"},
}


@bp.before_request
def verificar_acesso_escolar():
    """Guarda de entrada de todas as rotas do blueprint `escolar`.

    1. Exige um cabeçalho Authorization: Bearer <token> bem formado.
    2. Valida o token chamando o serviço auth (GET /me) — se a conta não
       existir, não estiver ativa, ou o token for inválido/expirado, a
       própria função de validação já devolve o erro certo (401/403/503).
    3. Guarda o utilizador autenticado em `g.utilizador` para as rotas
       seguintes poderem usar (ex: filtrar só os dados do próprio).
    4. Decide permissão: se a rota pedida estiver em PERMISSOES_PESSOAIS,
       só os perfis listados passam; caso contrário, só "admin" passa.
    """
    if request.endpoint is None:
        return None

    autorizacao = request.headers.get("Authorization", "")
    partes = autorizacao.split()

    if len(autorizacao) > 8192 or len(partes) != 2 or partes[0].lower() != "bearer":
        return jsonify({
            "error": "authentication_required",
            "message": "É necessário iniciar sessão.",
        }), 401, {"WWW-Authenticate": "Bearer"}

    utilizador, erro = obter_utilizador_da_sessao(partes[1])

    if erro is not None:
        return erro

    g.utilizador = utilizador

    if request.endpoint in PERMISSOES_PESSOAIS:
        if utilizador["perfil"] in PERMISSOES_PESSOAIS[request.endpoint]:
            return None

    elif utilizador["perfil"] == "admin":
        return None

    return jsonify({
        "error": "forbidden",
        "message": "Não tens permissão para realizar esta operação.",
    }), 403


@bp.after_request
def impedir_cache_dados_escolares(resposta):
    """Marca todas as respostas do blueprint como não-cacheáveis (dados escolares sensíveis)."""
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def obter_profissional_da_sessao():
    """Resolve o registo `profissionais` ligado à conta autenticada (g.utilizador).

    Faz duas verificações, não só uma: além de confirmar que existe um
    registo profissional associado a esta conta, confirma também que o
    perfil guardado nesse registo (docente/educadora/auxiliar) é o MESMO
    perfil que o auth devolveu para a conta agora. Isto protege contra um
    registo profissional desatualizado (ex: perfil mudou no auth depois de
    já ter sido criado o registo em escolar) continuar a dar acesso com um
    perfil que a conta já não tem.
    """
    import models.profissional as modelo_profissional

    profissional = modelo_profissional.obter_por_utilizador(ObjectId(g.utilizador["id"]))

    if profissional is None:
        return None, (
            jsonify({
                "error": "professional_profile_not_linked",
                "message": "A conta ainda não tem um registo profissional associado.",
            }),
            403,
        )

    if (
        g.utilizador.get("perfil") not in {"docente", "educadora", "auxiliar"}
        or profissional.get("perfil") != g.utilizador["perfil"]
    ):
        return None, (
            jsonify({
                "error": "professional_profile_mismatch",
                "message": "O perfil da conta não corresponde ao registo profissional.",
            }),
            403,
        )

    return profissional, None
