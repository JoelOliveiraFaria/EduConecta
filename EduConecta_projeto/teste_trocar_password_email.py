import json
import sys
import warnings

from getpass import getpass, GetPassWarning
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

warnings.simplefilter("error", GetPassWarning)
BASE = "http://127.0.0.1:8000"


def pedido(caminho, dados=None, token=None):
    headers = {}
    corpo = None

    if dados is not None:
        headers["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode("utf-8")

    if token:
        headers["Authorization"] = "Bearer " + token

    requisicao = Request(
        BASE + caminho,
        data=corpo,
        headers=headers,
        method="POST" if dados is not None else "GET",
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
            "Falha de ligação. Se já confirmaste a troca, "
            "não assumas que a palavra-passe antiga continua válida."
        )


def verificar(codigo, dados, esperado, descricao):
    if codigo != esperado:
        sys.exit(
            f"{descricao}: HTTP {codigo}; "
            f"{dados.get('message', 'resposta inesperada')}"
        )
    print("OK - " + descricao)


email = "emmadeoliveira260105@gmail.com"
temporaria = getpass("Palavra-passe temporária recebida por email: ")

codigo, dados = pedido("/login", {
    "email": email,
    "password": temporaria,
})
verificar(codigo, dados, 200, "Login com as credenciais recebidas")
token = dados["access_token"]

codigo, dados = pedido("/me", token=token)
verificar(codigo, dados, 403, "Acesso bloqueado antes da troca")

if dados.get("error") != "password_change_required":
    sys.exit("O bloqueio não corresponde à troca obrigatória.")

nova = getpass("Nova palavra-passe, entre 15 e 128 caracteres: ")
confirmacao = getpass("Repete a nova palavra-passe: ")

if nova != confirmacao:
    sys.exit("As palavras-passe não coincidem. Nada foi alterado.")

if not 15 <= len(nova) <= 128 or nova == temporaria:
    sys.exit(
        "A nova palavra-passe deve ter entre 15 e 128 caracteres "
        "e ser diferente da temporária. Nada foi alterado."
    )

if input("Confirmas a alteração desta conta? Escreve SIM: ").strip() != "SIM":
    sys.exit("Cancelado. Nada foi alterado.")

codigo, dados = pedido("/password/alterar", {
    "password_atual": temporaria,
    "password_nova": nova,
}, token)
verificar(codigo, dados, 200, "Palavra-passe alterada")

codigo, dados = pedido("/login", {
    "email": email,
    "password": temporaria,
})
verificar(codigo, dados, 401, "Palavra-passe temporária rejeitada")

codigo, dados = pedido("/login", {
    "email": email,
    "password": nova,
})
verificar(codigo, dados, 200, "Login com a nova palavra-passe")

codigo, dados = pedido("/me", token=dados["access_token"])
verificar(codigo, dados, 200, "Acesso permitido após a troca")

print("Primeiro acesso concluído. Guarda a nova palavra-passe.")