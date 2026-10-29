import json
import sys
import warnings

from getpass import getpass, GetPassWarning
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

warnings.simplefilter("error", GetPassWarning)

AUTH = "http://auth:8000"
SCHOOL = "http://escolar:8000"

EMAIL = "emmadeoliveira260105+docente@gmail.com"

TURMA_ATRIBUIDA = "6ae0caf50852a73f69bac39e"
OUTRA_TURMA = "6adf7f4f89f41c825d4b648c"
ALUNO_ESPERADO = "6ae0caf54d0d7ddbc83796c7"
PROFISSIONAL_ID = "6ae0cdcb898aa9fbfef0cdf6"


def pedido(base, caminho, metodo="GET", dados=None, token=None):
    headers = {}
    corpo = None

    if dados is not None:
        headers["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode("utf-8")

    if token:
        headers["Authorization"] = "Bearer " + token

    requisicao = Request(
        base + caminho,
        data=corpo,
        headers=headers,
        method=metodo,
    )

    try:
        with urlopen(requisicao, timeout=15) as resposta:
            return resposta.status, json.load(resposta)

    except HTTPError as erro:
        codigo = erro.code
        corpo = erro.read()
        erro.close()

        try:
            return codigo, json.loads(corpo)
        except ValueError:
            sys.exit(f"Resposta inesperada. HTTP {codigo}.")

    except (URLError, OSError):
        sys.exit("Falha de ligação. Envia o resultado antes de continuar.")


def verificar(resultado, esperado, descricao, erro=None):
    codigo, dados = resultado

    if codigo != esperado or (
        erro is not None and dados.get("error") != erro
    ):
        print("PASSO NÃO CONCLUÍDO:", descricao)
        print("HTTP:", codigo)
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        sys.exit(1)

    print("OK - " + descricao)
    return dados


password = getpass("Nova palavra-passe da conta docente: ")

dados = verificar(
    pedido(
        AUTH,
        "/login",
        "POST",
        {"email": EMAIL, "password": password},
    ),
    200,
    "Login do docente",
)
del password
token = dados["access_token"]

resultado = verificar(
    pedido(SCHOOL, "/me/turmas", token=token),
    200,
    "Consulta das próprias turmas",
)

turmas = resultado.get("turmas", [])

if (
    len(turmas) != 1
    or turmas[0].get("id") != TURMA_ATRIBUIDA
    or resultado.get("profissional", {}).get("id") != PROFISSIONAL_ID
):
    sys.exit(
        "A lista de turmas ou o profissional não corresponde "
        "às associações deste teste. Envia o resultado."
    )

print("OK - Apenas a turma atribuída aparece na lista")

resultado = verificar(
    pedido(
        SCHOOL,
        f"/me/turmas/{TURMA_ATRIBUIDA}/alunos",
        token=token,
    ),
    200,
    "Consulta dos alunos da turma atribuída",
)

alunos = resultado.get("alunos", [])

if (
    len(alunos) != 1
    or alunos[0].get("id") != ALUNO_ESPERADO
    or alunos[0].get("turma_id") != TURMA_ATRIBUIDA
):
    sys.exit("Os alunos devolvidos não correspondem ao teste.")

print("OK - O aluno devolvido pertence à turma atribuída")

verificar(
    pedido(
        SCHOOL,
        f"/me/turmas/{OUTRA_TURMA}/alunos",
        token=token,
    ),
    404,
    "Outra turma não é acessível pela rota pessoal",
    "class_not_accessible",
)

for caminho, descricao in [
    ("/alunos", "Lista geral de alunos bloqueada"),
    ("/turmas", "Lista geral de turmas bloqueada"),
    ("/profissionais", "Lista de profissionais bloqueada"),
    ("/encarregados", "Lista geral de encarregados bloqueada"),
    (
        f"/turmas/{OUTRA_TURMA}/alunos",
        "Rota administrativa de alunos da turma bloqueada",
    ),
    ("/me/alunos", "Área pessoal dos encarregados bloqueada"),
]:
    verificar(
        pedido(SCHOOL, caminho, token=token),
        403,
        descricao,
        "forbidden",
    )

verificar(
    pedido(
        SCHOOL,
        f"/turmas/{TURMA_ATRIBUIDA}/profissionais/{PROFISSIONAL_ID}",
        "PUT",
        token=token,
    ),
    403,
    "Docente não pode gerir associações de profissionais",
    "forbidden",
)

verificar(
    pedido(SCHOOL, "/me/turmas"),
    401,
    "Consulta de turmas sem autenticação bloqueada",
    "authentication_required",
)

print("TESTE CONCLUÍDO - Nenhum registo foi criado ou alterado.")