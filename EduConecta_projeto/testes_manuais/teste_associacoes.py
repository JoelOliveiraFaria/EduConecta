import json
import secrets
import sys
import warnings

from getpass import getpass, GetPassWarning
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

warnings.simplefilter("error", GetPassWarning)

AUTH = "http://auth:8000"
SCHOOL = "http://escolar:8000"


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
        sys.exit(
            "Falha de ligação. Podem existir registos já criados. "
            "Não repitas automaticamente; envia o resultado."
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


def login(email, descricao):
    password = getpass(f"Palavra-passe de {descricao}: ")

    dados = verificar(
        pedido(
            AUTH,
            "/login",
            "POST",
            {"email": email, "password": password},
        ),
        200,
        f"Login de {descricao}",
    )

    return dados["access_token"]


admin = login("admin@example.com", "administrador")
email = "emmadeoliveira260105@gmail.com"
encarregado_token = login(email, "a tua conta de teste")

conta = verificar(
    pedido(AUTH, "/me", token=encarregado_token),
    200,
    "Conta de teste disponível e com palavra-passe já alterada",
)

if conta.get("perfil") != "encarregado":
    sys.exit("A conta de teste não tem perfil encarregado.")

codigo, dados = pedido(
    SCHOOL,
    "/me/alunos",
    token=encarregado_token,
)

if codigo == 200:
    sys.exit(
        "Esta conta já tem um encarregado associado. "
        "Não foram criados novos registos. Envia esta mensagem."
    )

if codigo != 403 or dados.get("error") != "school_profile_not_linked":
    print("HTTP:", codigo)
    print(json.dumps(dados, ensure_ascii=False, indent=2))
    sys.exit("Não foi possível confirmar o estado inicial.")

print("Vamos criar um encarregado, um aluno e uma turma de teste.")
print("A conta que será associada é:", email)

if input("Escreve SIM para continuar: ").strip() != "SIM":
    sys.exit("Cancelado. Nenhum registo escolar foi criado.")

sufixo = secrets.token_hex(4)

encarregado = verificar(
    pedido(
        SCHOOL,
        "/encarregados",
        "POST",
        {"nome": "Responsável Teste EduConecta", "telefone": ""},
        admin,
    ),
    201,
    "Encarregado escolar criado",
)
print("ID do encarregado:", encarregado["id"])

verificar(
    pedido(
        SCHOOL,
        f"/encarregados/{encarregado['id']}/utilizador",
        "PUT",
        {"utilizador_id": conta["id"]},
        admin,
    ),
    200,
    "Conta ligada ao encarregado",
)

turma = verificar(
    pedido(
        SCHOOL,
        "/turmas",
        "POST",
        {
            "nome": f"Turma Teste {sufixo}",
            "ano_letivo": "2026/2027",
        },
        admin,
    ),
    201,
    "Turma criada",
)
print("ID da turma:", turma["id"])

aluno = verificar(
    pedido(
        SCHOOL,
        "/alunos",
        "POST",
        {
            "nome": "Educando Teste EduConecta",
            "numero_processo": f"ASSOC-{sufixo}",
        },
        admin,
    ),
    201,
    "Aluno criado",
)
print("ID do aluno:", aluno["id"])

verificar(
    pedido(
        SCHOOL,
        f"/alunos/{aluno['id']}/turma",
        "PUT",
        {"turma_id": turma["id"]},
        admin,
    ),
    200,
    "Aluno associado à turma",
)

verificar(
    pedido(
        SCHOOL,
        f"/alunos/{aluno['id']}/encarregados/{encarregado['id']}",
        "PUT",
        token=admin,
    ),
    200,
    "Encarregado associado ao aluno",
)

resultado = verificar(
    pedido(SCHOOL, "/me/alunos", token=encarregado_token),
    200,
    "Consulta dos educandos pela conta do encarregado",
)

if resultado.get("encarregado", {}).get("id") != encarregado["id"]:
    sys.exit("A consulta devolveu um encarregado inesperado.")

alunos = resultado.get("alunos", [])

if (
    len(alunos) != 1
    or alunos[0].get("id") != aluno["id"]
    or alunos[0].get("turma_id") != turma["id"]
):
    sys.exit("Os alunos ou a turma devolvidos não correspondem ao teste.")

print("OK - A conta vê exatamente o aluno e a turma associados")

verificar(
    pedido(SCHOOL, "/alunos", token=encarregado_token),
    403,
    "Lista geral de alunos continua bloqueada ao encarregado",
)

verificar(
    pedido(
        SCHOOL,
        f"/encarregados/{encarregado['id']}/utilizador",
        "PUT",
        {"utilizador_id": conta["id"]},
        encarregado_token,
    ),
    403,
    "Encarregado não pode gerir associações de contas",
)

print("TESTE CONCLUÍDO")
print("Os registos de teste foram mantidos na aplicação.")