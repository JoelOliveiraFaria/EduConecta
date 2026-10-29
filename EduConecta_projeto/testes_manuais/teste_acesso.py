import getpass
import json
import sys
from io import BytesIO
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image


def consultar(url, dados=None, token=None):
    headers = {"Accept": "application/json"}
    corpo = None

    if dados is not None:
        headers["Content-Type"] = "application/json"
        corpo = json.dumps(dados).encode("utf-8")

    if token:
        headers["Authorization"] = "Bearer " + token

    pedido = Request(url, data=corpo, headers=headers)

    try:
        with urlopen(pedido, timeout=15) as resposta:
            return json.load(resposta)

    except HTTPError as exc:
        print("\nHTTP", exc.code)
        print(exc.read().decode("utf-8", errors="replace"))
        sys.exit(1)

    except (URLError, TimeoutError, OSError) as exc:
        print("\nNão foi possível contactar o serviço:", exc)
        sys.exit(1)


email = input("Email da docente: ").strip()
password = getpass.getpass("Palavra-passe da docente: ")

sessao = consultar(
    "http://auth:8000/login",
    dados={"email": email, "password": password},
)
del password

perfil = sessao.get("utilizador", {}).get("perfil")

if perfil not in {"docente", "educadora"}:
    print("Esta conta não tem perfil de docente ou educadora.")
    sys.exit(1)

print("\nOK — sessão da docente iniciada.")

token_docente = sessao["access_token"]

turmas = consultar(
    "http://escolar:8000/me/turmas",
    token=token_docente,
)

lista_turmas = turmas.get("turmas", [])

if len(lista_turmas) != 1:
    print("Este teste espera exatamente uma turma.")
    sys.exit(1)

turma_id = lista_turmas[0]["id"]
print("OK — turma encontrada:", turma_id)

base = "http://comunicados:8000"
url_comunicados = f"{base}/turmas/{turma_id}/comunicados"

print("\nA criar um comunicado de teste...")

comunicado = consultar(
    url_comunicados,
    dados={
        "titulo": "Teste de fotografia",
        "texto": "Comunicado de teste sem dados pessoais.",
    },
    token=token_docente,
)

comunicado_id = comunicado["id"]
print("OK — comunicado criado:", comunicado_id)

with BytesIO() as memoria:
    with Image.new("RGB", (320, 240), "lightblue") as imagem:
        imagem.save(memoria, format="JPEG")
    imagem_bytes = memoria.getvalue()

fronteira = "EduConecta" + uuid4().hex

corpo_fotografia = (
    f"--{fronteira}\r\n"
    'Content-Disposition: form-data; name="fotografia"; '
    'filename="teste.jpg"\r\n'
    "Content-Type: image/jpeg\r\n"
    "\r\n"
).encode("utf-8")

corpo_fotografia += imagem_bytes
corpo_fotografia += f"\r\n--{fronteira}--\r\n".encode("utf-8")

url_fotografia = (
    f"{url_comunicados}/{comunicado_id}/fotografias"
)

pedido = Request(
    url_fotografia,
    data=corpo_fotografia,
    headers={
        "Authorization": "Bearer " + token_docente,
        "Content-Type": (
            "multipart/form-data; boundary=" + fronteira
        ),
        "Accept": "application/json",
    },
    method="POST",
)

print("\nA anexar a fotografia com a docente...")

try:
    with urlopen(pedido, timeout=30) as resposta:
        estado = resposta.status
        resultado = json.load(resposta)

except HTTPError as exc:
    print("\nERRO NO CARREGAMENTO — HTTP", exc.code)
    print(exc.read().decode("utf-8", errors="replace"))
    sys.exit(1)

except (URLError, TimeoutError, OSError) as exc:
    print("\nNão foi possível concluir o carregamento:", exc)
    sys.exit(1)

print("\nRESULTADO DO CARREGAMENTO — HTTP", estado)
print(json.dumps(resultado, ensure_ascii=False, indent=2))

print("\nTESTE DE PERMISSÕES — ENCARREGADO")

email_encarregado = input("Email do encarregado: ").strip()
password_encarregado = getpass.getpass(
    "Palavra-passe do encarregado: "
)

sessao_encarregado = consultar(
    "http://auth:8000/login",
    dados={
        "email": email_encarregado,
        "password": password_encarregado,
    },
)
del password_encarregado

if sessao_encarregado.get("utilizador", {}).get("perfil") != "encarregado":
    print("Esta conta não tem perfil de encarregado.")
    sys.exit(1)

pedido_encarregado = Request(
    url_fotografia,
    data=corpo_fotografia,
    headers={
        "Authorization": (
            "Bearer " + sessao_encarregado["access_token"]
        ),
        "Content-Type": (
            "multipart/form-data; boundary=" + fronteira
        ),
        "Accept": "application/json",
    },
    method="POST",
)

try:
    with urlopen(pedido_encarregado, timeout=30) as resposta:
        print(
            "\nFALHA NO TESTE — o encarregado conseguiu anexar.",
            "HTTP",
            resposta.status,
        )
        sys.exit(1)

except HTTPError as exc:
    conteudo = exc.read().decode("utf-8", errors="replace")

    print("\nRESULTADO DO ENCARREGADO — HTTP", exc.code)
    print(conteudo)

    if exc.code != 403:
        print("TESTE NÃO CONFIRMADO — esperávamos HTTP 403.")
        sys.exit(1)

    print("OK — o encarregado não pode anexar fotografias.")

except (URLError, TimeoutError, OSError) as exc:
    print("\nNão foi possível concluir o teste:", exc)
    sys.exit(1)