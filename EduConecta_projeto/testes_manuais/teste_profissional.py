import json
import sys
import warnings

from getpass import getpass, GetPassWarning
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

warnings.simplefilter("error", GetPassWarning)

AUTH = "http://auth:8000"
SCHOOL = "http://escolar:8000"

EMAIL_DOCENTE = "emmadeoliveira260105+docente@gmail.com"
TURMA_ID = "6ae0caf50852a73f69bac39e"


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
        with urlopen(requisicao, timeout=45) as resposta:
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
        sys.exit(
            "Falha de ligação. Podem existir registos já criados. "
            "Não repitas automaticamente."
        )


def verificar(resultado, esperado, descricao):
    codigo, dados = resultado

    if codigo != esperado:
        print("PASSO NÃO CONCLUÍDO:", descricao)
        print("HTTP:", codigo)
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        sys.exit(1)

    print("OK - " + descricao)
    return dados


password = getpass("Palavra-passe do administrador: ")

dados = verificar(
    pedido(
        AUTH,
        "/login",
        "POST",
        {"email": "admin@example.com", "password": password},
    ),
    200,
    "Login administrativo",
)
del password
token = dados["access_token"]

turma = verificar(
    pedido(
        SCHOOL,
        f"/turmas/{TURMA_ID}/alunos",
        token=token,
    ),
    200,
    "Turma de teste encontrada",
)

print("Destinatário das credenciais:", EMAIL_DOCENTE)
print("Perfil da nova conta: docente")
print("Turma:", turma["turma"]["nome"])
print("ID da turma:", TURMA_ID)
print("Serão criados uma conta e um registo profissional.")

if input("Confirmas? Escreve SIM: ").strip() != "SIM":
    sys.exit("Cancelado. Nenhum registo foi criado.")

conta = verificar(
    pedido(
        AUTH,
        "/admin/utilizadores",
        "POST",
        {
            "nome": "Docente Teste EduConecta",
            "email": EMAIL_DOCENTE,
            "perfil": "docente",
        },
        token,
    ),
    201,
    "Conta docente criada e email aceite pelo servidor",
)
print("ID da conta:", conta["id"])

profissional = verificar(
    pedido(
        SCHOOL,
        "/profissionais",
        "POST",
        {"utilizador_id": conta["id"]},
        token,
    ),
    201,
    "Registo profissional criado",
)
print("ID do profissional:", profissional["id"])

caminho = (
    f"/turmas/{TURMA_ID}/profissionais/"
    f"{profissional['id']}"
)

verificar(
    pedido(
        SCHOOL,
        caminho,
        "PUT",
        token=token,
    ),
    200,
    "Profissional associado à turma",
)

verificar(
    pedido(
        SCHOOL,
        caminho,
        "PUT",
        token=token,
    ),
    200,
    "Repetição da mesma associação aceite",
)

print("TESTE CONCLUÍDO")
print("Os registos foram mantidos na aplicação.")
print("Verifica o email com as credenciais da conta docente.")