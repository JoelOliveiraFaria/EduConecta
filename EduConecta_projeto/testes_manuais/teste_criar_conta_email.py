import json
import sys
import warnings

from getpass import getpass, GetPassWarning
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

warnings.simplefilter("error", GetPassWarning)

BASE = "http://127.0.0.1:8000"


def pedido(caminho, dados, token=None):
    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = "Bearer " + token

    requisicao = Request(
        BASE + caminho,
        data=json.dumps(dados).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(requisicao, timeout=45) as resposta:
            return resposta.status, json.load(resposta)

    except HTTPError as erro:
        codigo = erro.code
        corpo = erro.read().decode("utf-8")
        erro.close()

        try:
            dados_erro = json.loads(corpo)
        except ValueError:
            dados_erro = {"message": "Resposta de erro inesperada."}

        return codigo, dados_erro

    except (URLError, TimeoutError, OSError):
        sys.exit(
            "Não foi possível confirmar a resposta. "
            "Não repitas a criação sem verificar se a conta já existe."
        )


email_admin = input(
    "Email do administrador [admin@example.com]: "
).strip() or "admin@example.com"

password_admin = getpass(
    "Palavra-passe da conta de administrador: "
)

codigo, dados = pedido("/login", {
    "email": email_admin,
    "password": password_admin,
})
del password_admin

if codigo != 200 or not dados.get("access_token"):
    print("Login não concluído. HTTP:", codigo)
    print(dados.get("message", "Resposta inesperada."))
    sys.exit(1)

token = dados["access_token"]
print("Login administrativo concluído.")

destino = input(
    "Email teu para receber as credenciais da conta de teste: "
).strip()

if not destino:
    sys.exit("Email vazio. Nenhuma conta foi criada.")

print("Será criada uma conta de teste com perfil encarregado.")
print("Destinatário:", destino)

confirmacao = input(
    "Confirmas que controlas este email e queres criar a conta? [SIM]: "
).strip()

if confirmacao != "SIM":
    sys.exit("Cancelado. Nenhuma conta foi criada.")

codigo, dados = pedido(
    "/admin/utilizadores",
    {
        "nome": "Teste Envio EduConecta",
        "email": destino,
        "perfil": "encarregado",
    },
    token,
)

print("HTTP:", codigo)
print(json.dumps(dados, ensure_ascii=False, indent=2))

if codigo == 201:
    print("Conta criada. Verifica o email e a pasta de spam.")
else:
    print("Não repitas automaticamente. Envia o resultado para análise.")